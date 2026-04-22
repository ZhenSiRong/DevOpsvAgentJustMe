# SELinux Policy Module 设计文档 — DevOps Agent

> 本文件为 Phase 2 核心安全层的独立设计文档。实际策略文件将在后续阶段根据真机环境编译部署。

---

## 1. 设计目标

在麒麟高级服务器版 V11（默认 SELinux enforcing 模式）上，为 DevOps Agent 运行时进程建立**独立的安全策略域**，实现：

1. **进程级沙箱**：Agent 进程（运行 devops-agent 的 Python 进程）被限制在最小权限域中
2. **文件级隔离**：Agent 只能访问预授权的文件/目录，无法读写系统关键配置
3. **网络级控制**：Agent 的网络访问范围被明确限定（本地回环 + 特定端口）
4. **审计可追溯**：所有 SELinux AVC 拒绝事件可被 auditd 捕获

## 2. 策略架构

```
+-------------------------------------------------------------+
|                    devops_agent_t  (Domain)                  |
|  +-------------------------------------------------------+  |
|  |  Python 进程 (devops-agent)                            |  |
|  |  - 可以读取: /root/devops-agent/, /tmp/, /var/log/    |  |
|  |  - 可以写入: /root/devops-agent/data/, /tmp/          |  |
|  |  - 可以执行: /usr/bin/python3.12, /usr/bin/sudo       |  |
|  |  - 可以网络: lo (127.0.0.1), 特定端口 (8000, 22)      |  |
|  +-------------------------------------------------------+  |
+-------------------------------------------------------------+
              |
              |  AVC 拦截
              v
+-------------------------------------------------------------+
|  禁止访问: /etc/passwd, /etc/shadow, /boot/, /etc/selinux/  |
|  禁止执行: /bin/rm (直接), /sbin/fdisk, /sbin/mkfs.*       |
|  禁止网络: 外网出口（除非显式配置）                          |
+-------------------------------------------------------------+
```

## 3. 类型与角色定义

```te
# ========================================
#  类型定义
# ========================================

# Agent 运行时域
type devops_agent_t;
type devops_agent_exec_t;      # 可执行文件类型
type devops_agent_data_t;      # 数据文件类型

# Agent 可以访问的日志/临时文件类型
type devops_agent_tmp_t;       # 临时文件
type devops_agent_log_t;       # 日志文件

# ========================================
#  域切换规则
# ========================================

# 从 unconfined_t / sysadm_t 启动 Agent 时切换域
domain_type(devops_agent_t)
domain_entry_file(devops_agent_t, devops_agent_exec_t)

# Agent 域的基本能力（最小集）
allow devops_agent_t self:process { signal sigkill };
allow devops_agent_t self:fifo_file rw_fifo_file_perms;
allow devops_agent_t self:unix_stream_socket { create connect read write };
allow devops_agent_t self:tcp_socket { create connect read write };
allow devops_agent_t self:udp_socket { create connect read write };

# ========================================
#  文件访问规则
# ========================================

# Agent 可执行文件
allow devops_agent_t devops_agent_exec_t:file { read execute execute_no_trans };

# Agent 数据目录（项目代码、配置文件、数据库）
allow devops_agent_t devops_agent_data_t:dir { read search open add_name write };
allow devops_agent_t devops_agent_data_t:file { read write create append getattr };

# 临时文件
allow devops_agent_t devops_agent_tmp_t:dir { read search open add_name write };
allow devops_agent_t devops_agent_tmp_t:file { read write create append getattr unlink };

# 系统日志只读（journalctl 需要）
allow devops_agent_t var_log_t:dir search;
allow devops_agent_t var_log_t:file { read getattr open };

# /tmp 目录访问
allow devops_agent_t tmp_t:dir { search read open add_name write };
allow devops_agent_t tmp_t:file { read write create append getattr unlink };

# 读取系统状态（ps, df, free 等需要）
allow devops_agent_t proc_t:dir search;
allow devops_agent_t proc_t:file { read getattr open };
allow devops_agent_t sysfs_t:dir search;
allow devops_agent_t sysfs_t:file { read getattr open };

# 网络状态查看（netstat, ss 需要）
allow devops_agent_t proc_net_t:file { read getattr open };

# ========================================
#  网络访问规则
# ========================================

# 本地回环通信（FastAPI 内部、数据库本地连接）
allow devops_agent_t self:tcp_socket { accept listen bind connect };
allow devops_agent_t loopback_t:tcp_socket { accept listen bind connect };

# HTTP/HTTPS 出站（LLM API 调用需要）
allow devops_agent_t http_port_t:tcp_socket { name_connect };
allow devops_agent_t https_port_t:tcp_socket { name_connect };

# SSH 管理端口（如果需要远程执行）
# allow devops_agent_t ssh_port_t:tcp_socket { name_connect };

# ========================================
#  执行外部命令（通过 sudo/devops-runner）
# ========================================

# Agent 可以执行 sudo（切用户执行运维命令）
allow devops_agent_t sudo_exec_t:file { read execute };

# 可以执行基本系统工具（白名单方式）
allow devops_agent_t bin_t:file { read execute getattr };

# 禁止执行危险命令（通过白名单控制，不在白名单则 AVC 拒绝）
# /sbin 下的管理工具需要显式授权
# allow devops_agent_t sbin_t:file { read execute getattr };  # 默认禁止
```

## 4. 文件上下文标记（file_contexts）

```fc
# Agent 项目目录
/root/devops-agent(/.*)?          gen_context(system_u:object_r:devops_agent_data_t,s0)

# Agent 可执行入口（main.py / uvicorn 启动脚本）
/root/devops-agent/src/devops_agent/main\.py  gen_context(system_u:object_r:devops_agent_exec_t,s0)

# Agent 临时/缓存目录
/root/devops-agent/data(/.*)?     gen_context(system_u:object_r:devops_agent_data_t,s0)
/root/devops-agent/tmp(/.*)?      gen_context(system_u:object_r:devops_agent_tmp_t,s0)

# Agent 日志目录
/var/log/devops-agent(/.*)?       gen_context(system_u:object_r:devops_agent_log_t,s0)
```

## 5. 与现有安全层的协作

| 安全层 | 作用域 | 与 SELinux 的关系 |
|--------|--------|-------------------|
| `validator.py` 七层校验 | 应用层命令过滤 | 先通过正则拦截危险命令，SELinux 作为兜底 |
| `executor.py` sudo 切用户 | 进程执行权限 | Agent 以 devops-runner 用户运行，SELinux 限制该用户域 |
| `config_guard.py` 写保护 | 配置文件监控 | SELinux 的 file_contexts 提供底层文件类型隔离 |
| `prompt_injection.py` 输入过滤 | LLM 输入安全 | 与 SELinux 无关，互补层 |

## 6. 部署步骤（后续阶段执行）

```bash
# 1. 安装 policy 开发包（麒麟V11）
dnf install -y selinux-policy-devel policycoreutils policycoreutils-python-utils

# 2. 编译模块
make -f /usr/share/selinux/devel/Makefile devops_agent.pp

# 3. 安装模块
semodule -i devops_agent.pp

# 4. 标记文件上下文
restorecon -R /root/devops-agent/
restorecon -R /var/log/devops-agent/

# 5. 启动 Agent（自动进入 devops_agent_t 域）
runcon -t devops_agent_t python3 -m devops_agent

# 6. 验证
cat /var/log/audit/audit.log | grep devops_agent_t | grep denied
# 无 denied → 策略生效
```

## 7. 验收标准

- [ ] `ps -eZ | grep devops_agent` 显示进程运行在 `devops_agent_t` 域
- [ ] Agent 可以正常执行白名单内的运维命令（df/ps/netstat/journalctl）
- [ ] Agent 无法直接写入 `/etc/passwd`、`/etc/shadow`（AVC denied 日志）
- [ ] Agent 无法执行 `/sbin/fdisk`、`/sbin/mkfs.ext4`
- [ ] Agent 可以正常监听 8000 端口并处理 HTTP 请求
- [ ] Agent 可以访问外部 LLM API（HTTPS 出站）
- [ ] `semodule -l | grep devops_agent` 显示模块已加载

## 8. 风险与限制

1. **loongarch64 兼容性**：SELinux policy 编译工具链在 loongarch64 上需验证
2. **DNF 包可用性**：麒麟 V11 的 `selinux-policy-devel` 可能需要特定源
3. **开发工作量**：约 1-2 人周（策略编写 + 测试 + 调优）
4. **与现有 AppArmor 冲突**：麒麟 V11 默认使用 SELinux，不存在 AppArmor 冲突
5. **动态规则更新**：policy module 热更新需要重新编译加载，不能运行时修改
