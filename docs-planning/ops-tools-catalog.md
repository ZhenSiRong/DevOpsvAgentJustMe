# 运维场景常用工具目录（MCP Tool 封装候选清单）

> 本文档面向 DevOps Agent 的 MCP Tool 插件化设计，系统梳理 Linux 运维全场景中的核心命令工具，按"工具族 → 动作 → 参数 → 输出 → 安全等级"五维结构化，为后续 MCP Server 封装提供直接映射依据。
>
> 文档版本：v1.0  
> 覆盖范围：系统监控、日志分析、网络诊断、进程管理、文件系统、用户权限、安全审计、服务管理、容器运维、性能分析 10 大场景  
> 安全等级说明：
> - 🟢 只读 — 无风险，可直接开放给 Agent
> - 🟡 受限写 — 需确认/白名单/备份机制
> - 🔴 高危写 — 严格校验，建议人工审批

---

## 一、系统监控与资源查看

### 1.1 CPU / 内存 / 负载

| 工具 | 动作 | 典型用法 | 输出格式 | 安全等级 | MCP 封装建议 |
|------|------|----------|----------|----------|--------------|
| **top** | 实时进程资源排行 | `top -b -n1` | 文本表格 | 🟢 | `system_top` — 输出 CPU/内存占用最高的 N 个进程 |
| **ps** | 进程快照 | `ps aux`、`ps -eo pid,ppid,cmd,%mem,%cpu --sort=-%cpu` | 文本行 | 🟢 | `process_list`（已有）— 支持按 CPU/内存排序、过滤 |
| **free** | 内存用量 | `free -h`、`free -m` | 简洁表格 | 🟢 | `memory_usage` — 返回 total/used/free/shared/buff/cache/available |
| **uptime** | 系统负载 | `uptime` | 单行文本 | 🟢 | `system_uptime` — 返回 load average (1m, 5m, 15m) + 运行时长 |
| **vmstat** | 系统整体状态 | `vmstat 1 5` | 文本表格 | 🟢 | `system_vmstat` — 返回 procs/memory/swap/io/system/cpu 指标 |
| **sar** (sysstat) | 历史性能数据 | `sar -u 1 3`、`sar -r` | 文本表格 | 🟢 | `system_sar` — 需安装 sysstat，支持 CPU/内存/IO/网络历史 |

### 1.2 磁盘与 IO

| 工具 | 动作 | 典型用法 | 输出格式 | 安全等级 | MCP 封装建议 |
|------|------|----------|----------|----------|--------------|
| **df** | 文件系统用量 | `df -h`、`df -i` | 文本表格 | 🟢 | `disk_usage`（已有）— 返回各挂载点的容量/用量/剩余/使用率 |
| **du** | 目录大小 | `du -sh /var/log`、`du -d 1 -h /opt` | 文本行 | 🟢 | `directory_size` — 返回指定目录的总大小及子目录分布 |
| **iostat** | 磁盘 IO 统计 | `iostat -x 1 3` | 文本表格 | 🟢 | `disk_iostat` — 返回设备级读写速率/IOPS/队列深度/利用率 |
| **lsblk** | 块设备信息 | `lsblk`、`lsblk -f` | 树形文本 | 🟢 | `block_devices` — 返回磁盘/分区/挂载点/LVM 结构 |
| **fdisk -l** | 分区表 | `fdisk -l` | 文本块 | 🟢 | `partition_table` — 需 root，返回磁盘分区信息 |

### 1.3 网络连接与流量

| 工具 | 动作 | 典型用法 | 输出格式 | 安全等级 | MCP 封装建议 |
|------|------|----------|----------|----------|--------------|
| **ss** | Socket 统计 | `ss -tlnp`、`ss -s` | 文本表格 | 🟢 | `socket_list` — 替代 netstat，返回 TCP/UDP/UNIX 连接 |
| **netstat** | 网络连接 | `netstat -tlnp` | 文本表格 | 🟢 | 同上，兼容性工具 |
| **ip** | 网络配置 | `ip addr`、`ip route`、`ip link` | 文本块 | 🟢 | `network_interfaces`（已有）— 返回 IP/路由/MAC/状态 |
| **nload** / **iftop** | 实时流量 | `iftop -i eth0` | 交互式 | 🟢 | 暂不封装（交互式工具不适合 Agent） |
| **nstat** / **ss -i** | TCP 连接详情 | `ss -i` | 文本表格 | 🟢 | `tcp_connection_details` — 返回 RTT/拥塞窗口等 |

---

## 二、日志分析

### 2.1 系统日志

| 工具 | 动作 | 典型用法 | 输出格式 | 安全等级 | MCP 封装建议 |
|------|------|----------|----------|----------|--------------|
| **journalctl** | systemd 日志 | `journalctl -u nginx -n 100 --since "1 hour ago"` | 文本行 | 🟢 | `query_logs`（已有）— 支持 unit/time/level/priority 过滤 |
| **journalctl** | 日志导出 | `journalctl --since "2024-01-01" --until "2024-01-02" > backup.log` | 文件 | 🟡 | `export_logs` — 导出指定时间段日志到文件 |
| **dmesg** | 内核环形缓冲 | `dmesg -T --level=err,warn` | 文本行 | 🟢 | `kernel_messages` — 返回内核错误/警告信息 |

### 2.2 文件级日志操作

| 工具 | 动作 | 典型用法 | 输出格式 | 安全等级 | MCP 封装建议 |
|------|------|----------|----------|----------|--------------|
| **tail** | 实时/尾部查看 | `tail -f /var/log/nginx/access.log`、`tail -n 100` | 文本流/行 | 🟢 | `tail_file`（已有）— 支持 follow 模式（SSE 推送） |
| **grep** | 内容过滤 | `grep -i "error" /var/log/app.log` | 匹配行 | 🟢 | `log_grep` — 支持正则/忽略大小写/上下文行 |
| **awk** | 字段提取 | `awk '{print $1, $9}' access.log` | 文本行 | 🟢 | `log_extract` — 按字段/分隔符提取 |
| **sed** | 内容替换/删除 | `sed -n '100,200p' huge.log` | 文本行 | 🟢 | `log_slice` — 按行号范围提取 |
| **wc** | 行数/字数统计 | `wc -l access.log` | 数字 | 🟢 | `log_count` — 返回日志总行数/匹配行数 |
| **zgrep** | 压缩日志搜索 | `zgrep "error" /var/log/nginx/access.log.1.gz` | 匹配行 | 🟢 | `compressed_log_grep` — 支持 .gz/.bz2/.xz |

### 2.3 日志轮转与管理

| 工具 | 动作 | 典型用法 | 输出格式 | 安全等级 | MCP 封装建议 |
|------|------|----------|----------|----------|--------------|
| **logrotate** | 手动触发轮转 | `logrotate -f /etc/logrotate.d/nginx` | 无输出 | 🟡 | `rotate_logs` — 需配置文件存在，触发日志轮转 |
| **logrotate -d** | 测试配置 | `logrotate -d /etc/logrotate.conf` | 调试文本 | 🟢 | `check_logrotate_config` — 验证配置语法 |

---

## 三、网络诊断

### 3.1 连通性与路由

| 工具 | 动作 | 典型用法 | 输出格式 | 安全等级 | MCP 封装建议 |
|------|------|----------|----------|----------|--------------|
| **ping** | 连通性测试 | `ping -c 4 8.8.8.8` | 统计文本 | 🟢 | `ping_host`（已有）— 返回丢包率/RTT min/avg/max |
| **traceroute** | 路由追踪 | `traceroute -n google.com` | 逐跳文本 | 🟢 | `trace_route` — 返回每跳 IP/延迟/状态 |
| **mtr** | 综合路由诊断 | `mtr -r -c 10 google.com` | 报告文本 | 🟢 | `mtr_report` — 结合 ping + traceroute 的报告 |
| **curl** | HTTP 探测 | `curl -I -s -o /dev/null -w "%{http_code}" http://localhost:8080` | 数字/头 | 🟢 | `http_probe` — 返回状态码/响应头/响应时间 |
| **wget** | HTTP 下载测试 | `wget --spider http://example.com` | 文本 | 🟢 | 与 curl 功能重叠，建议优先 curl |

### 3.2 DNS 解析

| 工具 | 动作 | 典型用法 | 输出格式 | 安全等级 | MCP 封装建议 |
|------|------|----------|----------|----------|--------------|
| **dig** | DNS 查询 | `dig @8.8.8.8 example.com A`、`dig -x 8.8.8.8` | 详细文本 | 🟢 | `dns_resolve`（已有）— 支持 A/AAAA/MX/NS/PTR/TXT |
| **nslookup** | DNS 查询 | `nslookup example.com` | 简洁文本 | 🟢 | 同上，兼容性工具 |
| **host** | DNS 查询 | `host example.com` | 单行文本 | 🟢 | 同上 |
| **getent** | 名称服务查询 | `getent hosts example.com` | 文本 | 🟢 | `getent_query` — 支持 hosts/passwd/group/services |

### 3.3 深度网络抓包

| 工具 | 动作 | 典型用法 | 输出格式 | 安全等级 | MCP 封装建议 |
|------|------|----------|----------|----------|--------------|
| **tcpdump** | 抓包 | `tcpdump -i eth0 port 80 -c 100 -w capture.pcap` | pcap 文件 | 🟡 | `capture_traffic` — 需 root，支持过滤表达式/数量限制/时长限制 |
| **tcpdump** | 实时分析 | `tcpdump -i any -nn -c 20` | 文本流 | 🟢 | `capture_preview` — 不保存文件，仅输出摘要 |

---

## 四、进程与服务管理

### 4.1 进程查看与操作

| 工具 | 动作 | 典型用法 | 输出格式 | 安全等级 | MCP 封装建议 |
|------|------|----------|----------|----------|--------------|
| **ps** | 进程列表 | `ps aux`、`ps -eo pid,comm,pcpu,pmem --sort=-pcpu` | 文本表格 | 🟢 | `process_list`（已有）— 支持排序/过滤/字段定制 |
| **pgrep** | 按名查找 PID | `pgrep -a nginx`、`pgrep -u root sshd` | PID 列表 | 🟢 | `process_find` — 返回匹配进程的 PID/命令行 |
| **pidstat** | 进程级资源统计 | `pidstat -u -p 1234 1 5` | 文本表格 | 🟢 | `process_stat` — 返回指定进程的 CPU/内存/IO 统计 |
| **pstree** | 进程树 | `pstree -p` | 树形文本 | 🟢 | `process_tree` — 展示父子进程关系 |
| **lsof** | 打开文件 | `lsof -p 1234`、`lsof -i :80`、`lsof /var/log` | 文本表格 | 🟢 | `list_open_files` — 返回进程打开的文件/端口/连接 |
| **fuser** | 占用文件的进程 | `fuser -v /var/log/messages` | 文本 | 🟢 | `file_users` — 返回占用指定文件/端口的进程 |

### 4.2 进程控制（⚠️ 危险操作）

| 工具 | 动作 | 典型用法 | 输出格式 | 安全等级 | MCP 封装建议 |
|------|------|----------|----------|----------|--------------|
| **kill** | 发送信号 | `kill -TERM 1234`、`kill -9 1234` | 无 | 🔴 | `process_kill` — **需安全校验**：确认目标 PID 存在、白名单信号、禁止 kill -9 系统进程 |
| **pkill** | 按名杀进程 | `pkill -f "python app.py"` | 无 | 🔴 | 同上，**需额外校验**：避免通配符误杀 |
| **killall** | 按名杀全部 | `killall nginx` | 无 | 🔴 | 同上，风险更高 |
| **nice** / **renice** | 调整优先级 | `renice -n 10 -p 1234` | 无 | 🟡 | `process_renice` — 限制优先级范围（-20~19） |

### 4.3 systemd 服务管理

| 工具 | 动作 | 典型用法 | 输出格式 | 安全等级 | MCP 封装建议 |
|------|------|----------|----------|----------|--------------|
| **systemctl status** | 查看服务状态 | `systemctl status nginx` | 文本块 | 🟢 | `service_status` — 返回 active/inactive/failed + 最近日志 |
| **systemctl list-units** | 列出服务 | `systemctl list-units --type=service --state=failed` | 文本表格 | 🟢 | `service_list` — 支持按类型/状态过滤 |
| **systemctl start/stop/restart** | 启停服务 | `systemctl restart nginx` | 无 | 🟡 | `service_control` — **需白名单**：只允许预定义服务 |
| **systemctl enable/disable** | 开机自启 | `systemctl enable nginx` | 无 | 🟡 | `service_autostart` — **需白名单** |
| **systemctl daemon-reload** | 重载配置 | `systemctl daemon-reload` | 无 | 🟡 | `service_reload` —  reload systemd 配置 |
| **journalctl -u** | 服务日志 | `journalctl -u nginx -f` | 文本流 | 🟢 | `service_logs` — 与 query_logs 合并或独立封装 |

---

## 五、文件系统操作

### 5.1 只读查看

| 工具 | 动作 | 典型用法 | 输出格式 | 安全等级 | MCP 封装建议 |
|------|------|----------|----------|----------|--------------|
| **ls** | 列出目录 | `ls -la /var/log`、`ls -lt` | 文本表格 | 🟢 | `list_directory`（已有）— 支持排序/过滤/详细模式 |
| **find** | 文件搜索 | `find /var/log -name "*.log" -mtime +7` | 路径列表 | 🟢 | `find_files` — 支持 name/type/size/mtime/user/权限过滤 |
| **stat** | 文件元信息 | `stat /etc/passwd` | 文本块 | 🟢 | `file_stat` — 返回大小/权限/时间/链接数/inode |
| **file** | 文件类型 | `file /usr/bin/python3` | 单行文本 | 🟢 | `file_type` — 返回 MIME 类型/编码 |
| **readlink** | 解析软链 | `readlink -f /usr/bin/python` | 路径 | 🟢 | `resolve_symlink` — 返回真实路径 |
| **md5sum** / **sha256sum** | 文件校验 | `sha256sum /etc/passwd` | hash + 路径 | 🟢 | `file_checksum` — 返回文件哈希值 |

### 5.2 文件读写（⚠️ 受限操作）

| 工具 | 动作 | 典型用法 | 输出格式 | 安全等级 | MCP 封装建议 |
|------|------|----------|----------|----------|--------------|
| **cat** | 读取文件 | `cat /var/log/nginx/error.log` | 完整内容 | 🟢 | `read_file`（已有）— 支持限制行数/偏移 |
| **head** | 读取头部 | `head -n 50 large.log` | 前 N 行 | 🟢 | `read_file_head` — 或合并到 read_file |
| **touch** | 创建空文件 | `touch /tmp/flag` | 无 | 🟡 | `create_file` — 需限制在 /tmp 等安全目录 |
| **cp** | 复制文件 | `cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.bak` | 无 | 🟡 | `copy_file` — 需源文件可读、目标目录可写 |
| **mv** | 移动/重命名 | `mv old.log old.log.1` | 无 | 🟡 | `move_file` — 同上 |
| **rm** | 删除文件 | `rm /tmp/old.log` | 无 | 🔴 | **不建议封装** — 极高风险，Agent 不应直接删除文件 |
| **truncate** | 清空/截断 | `truncate -s 0 /tmp/big.log` | 无 | 🔴 | **不建议封装** |
| **mkdir** | 创建目录 | `mkdir -p /tmp/test/nested` | 无 | 🟡 | `create_directory` — 限制在安全目录 |
| **rmdir** | 删除空目录 | `rmdir /tmp/empty` | 无 | 🔴 | **不建议封装** |

### 5.3 大文件/磁盘清理

| 工具 | 动作 | 典型用法 | 输出格式 | 安全等级 | MCP 封装建议 |
|------|------|----------|----------|----------|--------------|
| **find + -size** | 查找大文件 | `find /var -type f -size +100M` | 路径列表 | 🟢 | `large_files`（已有）— 按大小阈值查找 |
| **find + -mtime** | 查找旧文件 | `find /tmp -type f -mtime +30` | 路径列表 | 🟢 | `old_files` — 按时间阈值查找 |
| **find + -delete** | 删除匹配文件 | `find /tmp -name "*.tmp" -mtime +7 -delete` | 无 | 🔴 | **不建议封装** — 自动删除风险太高 |

---

## 六、用户与权限管理

| 工具 | 动作 | 典型用法 | 输出格式 | 安全等级 | MCP 封装建议 |
|------|------|----------|----------|----------|--------------|
| **whoami** | 当前用户 | `whoami` | 用户名 | 🟢 | `current_user` — 返回当前执行用户 |
| **who** / **w** | 登录用户 | `who`、`w` | 文本表格 | 🟢 | `logged_in_users` — 返回登录会话列表 |
| **last** | 登录历史 | `last -n 20` | 文本表格 | 🟢 | `login_history` — 返回最近登录记录 |
| **id** | 用户信息 | `id devops-runner` | 文本 | 🟢 | `user_info` — 返回 UID/GID/所属组 |
| **groups** | 用户组 | `groups devops-runner` | 文本 | 🟢 | 合并到 user_info |
| **getent** | 查询用户/组 | `getent passwd devops-runner` | 文本 | 🟢 | `getent_query` — 支持 passwd/group/shadow(需 root) |
| **sudo -l** | sudo 权限 | `sudo -l -U devops-runner` | 文本 | 🟢 | `sudo_permissions` — 返回用户可执行的 sudo 命令 |
| **chown** | 修改所有者 | `chown user:group file` | 无 | 🟡 | `change_owner` — 需限制目标路径 |
| **chmod** | 修改权限 | `chmod 644 file`、`chmod +x script.sh` | 无 | 🟡 | `change_mode` — 需校验权限模式合法性 |

---

## 七、安全审计

| 工具 | 动作 | 典型用法 | 输出格式 | 安全等级 | MCP 封装建议 |
|------|------|----------|----------|----------|--------------|
| **ausearch** | audit 日志查询 | `ausearch -ts recent -m USER_LOGIN` | 文本行 | 🟢 | `audit_search` — 需 auditd 运行 |
| **auditctl** | audit 规则管理 | `auditctl -l` | 文本 | 🟢 | `audit_rules` — 查看当前审计规则 |
| **sestatus** | SELinux 状态 | `sestatus` | 文本 | 🟢 | `selinux_status` — 返回 mode/enabled 状态 |
| **getenforce** | SELinux 模式 | `getenforce` | 单行 | 🟢 | 合并到 sestatus |
| **semanage** | SELinux 策略 | `semanage login -l` | 文本表格 | 🟢 | `selinux_logins` — 返回用户登录映射 |
| **lastb** | 失败登录 | `lastb -n 20` | 文本表格 | 🟢 | `failed_logins` — 返回暴力破解尝试记录 |
| **faillock** | 登录失败锁定 | `faillock --user root` | 文本 | 🟢 | `account_lock_status` — 返回失败次数/锁定状态 |

---

## 八、软件包管理

| 工具 | 动作 | 典型用法 | 输出格式 | 安全等级 | MCP 封装建议 |
|------|------|----------|----------|----------|--------------|
| **dnf list** | 列出已安装包 | `dnf list installed` | 文本表格 | 🟢 | `list_packages` — 返回已安装软件包列表 |
| **dnf info** | 包详情 | `dnf info nginx` | 文本块 | 🟢 | `package_info` — 返回版本/描述/依赖 |
| **dnf search** | 搜索包 | `dnf search nginx` | 文本表格 | 🟢 | `search_packages` — 按关键词搜索 |
| **dnf install** | 安装包 | `dnf install -y nginx` | 文本流 | 🟡 | `install_package` — **需白名单/确认** |
| **dnf remove** | 卸载包 | `dnf remove nginx` | 文本流 | 🔴 | **不建议封装** — 卸载可能导致系统故障 |
| **dnf update** | 更新包 | `dnf update -y` | 文本流 | 🔴 | **不建议封装** — 批量更新风险高 |
| **rpm -qa** | 列出所有 RPM | `rpm -qa | grep nginx` | 文本行 | 🟢 | `list_rpms` — 底层包查询 |
| **rpm -qf** | 查询文件所属包 | `rpm -qf /usr/bin/nginx` | 包名 | 🟢 | `file_owner_package` — 返回文件所属的 RPM 包 |
| **pip3 list** | Python 包列表 | `pip3 list` | 文本表格 | 🟢 | `list_pip_packages` — 返回 pip 已安装包 |
| **pip3 show** | Python 包详情 | `pip3 show requests` | 文本块 | 🟢 | `pip_package_info` — 返回版本/位置/依赖 |

---

## 九、定时任务

| 工具 | 动作 | 典型用法 | 输出格式 | 安全等级 | MCP 封装建议 |
|------|------|----------|----------|----------|--------------|
| **crontab -l** | 查看当前用户 crontab | `crontab -l` | 文本 | 🟢 | `list_cron_jobs` — 返回当前用户的定时任务 |
| **crontab -e** | 编辑 crontab | `crontab -e` | 交互式 | 🔴 | **不建议封装** — 交互式编辑不适合 Agent |
| **crontab** (管道写入) | 设置 crontab | `echo "* * * * * /bin/echo hello" | crontab -` | 🔴 | **不建议封装** — 覆盖式写入风险高 |
| **atq** | 查看 at 队列 | `atq` | 文本表格 | 🟢 | `list_at_jobs` — 返回一次性任务队列 |
| **systemctl list-timers** | 查看 systemd timer | `systemctl list-timers --all` | 文本表格 | 🟢 | `list_systemd_timers` — 返回定时器任务 |

---

## 十、容器与虚拟化运维

| 工具 | 动作 | 典型用法 | 输出格式 | 安全等级 | MCP 封装建议 |
|------|------|----------|----------|----------|--------------|
| **docker ps** | 列出容器 | `docker ps -a` | 文本表格 | 🟢 | `docker_list_containers` — 返回容器列表及状态 |
| **docker inspect** | 容器详情 | `docker inspect nginx` | JSON | 🟢 | `docker_inspect` — 返回容器完整元数据 |
| **docker logs** | 容器日志 | `docker logs -f --tail 100 nginx` | 文本流 | 🟢 | `docker_logs` — 支持 follow/ tail/ since |
| **docker stats** | 容器资源 | `docker stats --no-stream` | 文本表格 | 🟢 | `docker_stats` — 返回容器 CPU/内存/IO/网络 |
| **docker top** | 容器内进程 | `docker top nginx` | 文本表格 | 🟢 | `docker_top` — 返回容器内进程列表 |
| **docker images** | 镜像列表 | `docker images` | 文本表格 | 🟢 | `docker_list_images` — 返回镜像列表 |
| **docker network ls** | 网络列表 | `docker network ls` | 文本表格 | 🟢 | `docker_list_networks` — 返回网络列表 |
| **docker volume ls** | 卷列表 | `docker volume ls` | 文本表格 | 🟢 | `docker_list_volumes` — 返回卷列表 |
| **docker exec** | 容器内执行 | `docker exec nginx nginx -t` | 命令输出 | 🟡 | `docker_exec` — **需命令白名单** |
| **docker start/stop/restart** | 容器启停 | `docker restart nginx` | 无 | 🟡 | `docker_container_control` — **需白名单** |
| **podman** | Podman 等价命令 | `podman ps`、`podman logs` | 同上 | 同上 | 与 docker 命令集基本一致，可加 `--compat` 模式 |
| **kubectl** | K8s 运维 | `kubectl get pods -n default` | 文本表格 | 🟡 | **单独设计 K8s MCP Server** — 工具集过大 |
| **crictl** | CRI 容器操作 | `crictl ps`、`crictl logs` | 文本表格 | 🟡 | 与 docker 命令集类似，用于 containerd/cri-o |

---

## 十一、性能分析与调试

| 工具 | 动作 | 典型用法 | 输出格式 | 安全等级 | MCP 封装建议 |
|------|------|----------|----------|----------|--------------|
| **perf** | 性能剖析 | `perf top`、`perf record -g -p 1234` | 交互式/文件 | 🟢 | `perf_top` / `perf_record` — 需安装 perf |
| **strace** | 系统调用追踪 | `strace -p 1234 -e trace=network` | 文本流 | 🟢 | `strace_process` — 追踪指定进程的系统调用 |
| **ltrace** | 库调用追踪 | `ltrace -p 1234` | 文本流 | 🟢 | `ltrace_process` — 追踪库函数调用 |
| **valgrind** | 内存检测 | `valgrind --leak-check=full ./program` | 文本 | 🟢 | 暂不封装（需编译程序配合） |
| **gdb** | 调试器 | `gdb -p 1234 -batch -ex "bt"` | 文本 | 🟡 | `gdb_backtrace` — 获取进程调用栈 |

---

## 十二、备份与同步

| 工具 | 动作 | 典型用法 | 输出格式 | 安全等级 | MCP 封装建议 |
|------|------|----------|----------|----------|--------------|
| **tar** | 打包压缩 | `tar -czf backup.tar.gz /etc/nginx` | 归档文件 | 🟡 | `create_archive` — 需限制源目录、输出到安全路径 |
| **tar** | 解压 | `tar -xzf backup.tar.gz -C /tmp` | 无 | 🟡 | `extract_archive` — 需校验目标路径安全性 |
| **rsync** | 增量同步 | `rsync -avz /src/ /dst/` | 文本 | 🟡 | `rsync_sync` — 需限制源/目标路径 |
| **scp** | 远程复制 | `scp file user@host:/path` | 文本 | 🟡 | 暂不封装（涉及远程认证） |
| **dd** | 磁盘克隆 | `dd if=/dev/sda of=/backup/sda.img bs=4M` | 进度 | 🔴 | **不建议封装** — 极易误操作 |

---

## 十三、硬件与设备

| 工具 | 动作 | 典型用法 | 输出格式 | 安全等级 | MCP 封装建议 |
|------|------|----------|----------|----------|--------------|
| **lscpu** | CPU 信息 | `lscpu` | 文本块 | 🟢 | `cpu_info` — 返回架构/核心数/频率/缓存 |
| **lsmem** | 内存信息 | `lsmem` | 文本块 | 🟢 | `memory_info` — 返回内存条分布 |
| **lspci** | PCI 设备 | `lspci -v` | 文本块 | 🟢 | `pci_devices` — 返回网卡/GPU/存储控制器 |
| **lsusb** | USB 设备 | `lsusb` | 文本表格 | 🟢 | `usb_devices` — 返回 USB 设备列表 |
| **dmidecode** | DMI 信息 | `dmidecode -t memory` | 文本块 | 🟢 | `dmi_info` — 需 root，返回硬件详细信息 |
| **hdparm** | 磁盘参数 | `hdparm -I /dev/sda` | 文本块 | 🟢 | `disk_parameters` — 返回磁盘型号/缓存/支持特性 |
| **smartctl** | 磁盘健康 | `smartctl -a /dev/sda` | 文本块 | 🟢 | `disk_smart` — 返回 SMART 健康数据 |
| **ethtool** | 网卡参数 | `ethtool eth0`、`ethtool -S eth0` | 文本块 | 🟢 | `nic_info` / `nic_stats` — 返回网卡配置/统计 |
| **ipmitool** | 带外管理 | `ipmitool sensor list` | 文本表格 | 🟡 | `ipmi_sensors` — 返回温度/电压/风扇状态 |

---

## 十四、MCP Tool 封装优先级矩阵

| 优先级 | 场景 | 候选 Tool 数量 | 理由 |
|--------|------|---------------|------|
| **P0（必须）** | 系统监控 | 8 | 赛题核心需求：OS 环境感知 |
| **P0（必须）** | 日志分析 | 6 | 赛题核心需求：journalctl/tail/grep |
| **P0（必须）** | 进程管理 | 5 | 赛题核心需求：ps/top/lsof |
| **P0（必须）** | 网络诊断 | 5 | 赛题核心需求：ping/netstat/ss |
| **P1（重要）** | 服务管理 | 5 | systemd 是麒麟 V11 核心 |
| **P1（重要）** | 文件系统 | 6 | 只读操作安全，写操作受限 |
| **P1（重要）** | 安全审计 | 5 | SELinux 是赛题关键约束 |
| **P2（增强）** | 容器运维 | 10 | 加分项，展示现代化运维能力 |
| **P2（增强）** | 性能分析 | 4 | 加分项，深度诊断能力 |
| **P2（增强）** | 硬件信息 | 7 | 加分项，国产化硬件适配 |
| **P3（可选）** | 包管理 | 5 | 日常运维，非演示重点 |
| **P3（可选）** | 备份同步 | 3 | 日常运维，非演示重点 |

---

## 十五、安全设计约束（MCP 封装时必须遵守）

### 15.1 命令白名单

Agent 自动执行的所有命令必须经过白名单校验。建议每个场景一个白名单组：

```
system.read  = [top, ps, free, uptime, vmstat, df, du, iostat, lsblk]
system.write = [systemctl restart, systemctl start, systemctl stop]  # 需二次确认
network.read = [ping, traceroute, curl, dig, ss, netstat, ip addr, ip route]
log.read     = [journalctl, tail, grep, awk, sed, wc, zgrep]
file.read    = [ls, find, stat, file, cat, head, md5sum]
file.write   = [cp, mv, mkdir, touch]  # 需路径白名单
process.read = [ps, pgrep, pidstat, pstree, lsof, fuser]
process.ctrl = [kill -TERM]  # 禁止 kill -9，禁止杀系统进程
```

### 15.2 危险命令黑名单（Agent 禁止执行）

以下命令**永远不应**封装为 Agent 可调用的 MCP Tool：

| 命令 | 风险 |
|------|------|
| `rm` / `rm -rf` | 不可逆数据销毁 |
| `dd` | 磁盘覆写/误克隆 |
| `mkfs` / `fdisk` (写操作) | 文件系统破坏 |
| `>` / `>>` 重定向到系统文件 | 配置破坏 |
| `chmod 777 /` | 权限失控 |
| `chown -R` 到系统目录 | 所有权混乱 |
| `dnf remove` / `yum remove` | 依赖断裂 |
| `pip uninstall` 系统包 | Python 环境破坏 |
| `crontab` 管道写入 | 任务覆盖 |
| `userdel` / `groupdel` 系统账户 | 账户丢失 |

### 15.3 输出安全

- 所有命令输出必须经过编码校验（防止二进制数据破坏 JSON）
- 输出长度限制（默认 5000 字符，超长截断并提示）
- 敏感信息过滤（自动 mask 密码、Token、AK/SK）

### 15.4 执行上下文隔离

- Agent 执行的命令必须以 `devops-runner` 用户身份运行（非 root）
- 写操作必须记录审计日志（who/what/when/result）
- 关键操作（服务启停、文件写）需先备份（`.bak.<timestamp>`）

---

## 十六、附录：MCP Tool Schema 设计模板

每个封装为 MCP Tool 的命令，建议按以下 JSON Schema 定义：

```json
{
  "name": "process_list",
  "description": "列出系统进程，支持按 CPU/内存排序和关键词过滤",
  "inputSchema": {
    "type": "object",
    "properties": {
      "sort_by": {
        "type": "string",
        "enum": ["cpu", "mem", "pid", "time"],
        "description": "排序字段",
        "default": "cpu"
      },
      "limit": {
        "type": "integer",
        "description": "最大返回进程数",
        "default": 20
      },
      "filter": {
        "type": "string",
        "description": "进程名关键词过滤（支持正则）"
      },
      "user": {
        "type": "string",
        "description": "按用户名过滤"
      }
    }
  }
}
```

输出格式建议统一为结构化 JSON：

```json
{
  "success": true,
  "data": [...],
  "summary": {
    "total": 156,
    "filtered": 20,
    "command": "ps aux --sort=-%cpu | head -21"
  },
  "truncated": false
}
```

---

*文档维护：新增 Tool 封装时，在此目录中登记；移除 Tool 时标注废弃原因。*
