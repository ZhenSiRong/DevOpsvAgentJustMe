"""
路由 2/7：OS 探针只读接口

GET  /api/v1/probe/disk      — 磁盘使用率 + 大文件扫描
GET  /api/v1/probe/processes — 进程列表/详情
GET  /api/v1/probe/network   — 网络连接 + 接口 + DNS
GET  /api/v1/probe/logs      — 系统日志查询 (journalctl/tail/grep)
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Query, HTTPException

from ...probe import (
    disk_usage, large_files,
    process_list, process_detail,
    network_connections, network_interfaces, dns_resolve,
    journal_logs, tail_file, grep_log,
)
from ..schemas import APIResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/probe", tags=["OS 探针"])


# ---- 磁盘探针 ----

@router.get("/disk", response_model=APIResponse, summary="磁盘使用率")
async def probe_disk(path: str = "/") -> APIResponse:
    """
    获取指定路径的磁盘使用情况。

    返回总空间、已用、可用、使用率百分比，以及最大的 N 个文件。
    所有操作均为只读，不修改任何系统状态。
    """
    try:
        usage = await disk_usage(path=path)
        big_files = await large_files(path=path, limit=10)
        return APIResponse(
            data={
                "usage": usage.to_dict() if hasattr(usage, "to_dict") else usage,
                "large_files": [
                    f.to_dict() if hasattr(f, "to_dict") else f for f in big_files
                ],
                "path": path,
            }
        )
    except PermissionError as e:
        logger.warning("磁盘探针权限不足: %s", e)
        raise HTTPException(status_code=403, detail=f"权限不足: {e}")
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"路径不存在: {path}")
    except Exception as e:
        logger.error("磁盘探针异常: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"探针执行异常: {e}")


# ---- 进程探针 ----

@router.get("/processes", response_model=APIResponse, summary="进程列表")
async def probe_processes(
    filter_by_name: str | None = None,
    pid: int | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> APIResponse:
    """
    获取系统进程列表。

    支持按名称模糊过滤或按 PID 精确查询单个进程详情。
    只读操作。
    """
    try:
        if pid is not None:
            # 单个进程详情
            detail = await process_detail(pid=pid)
            return APIResponse(data={
                "process": detail.to_dict() if hasattr(detail, "to_dict") else detail,
            })

        # 进程列表
        processes = await process_list(filter_str=filter_by_name, limit=limit)
        return APIResponse(data={
            "processes": [
                p.to_dict() if hasattr(p, "to_dict") else p for p in processes
            ],
            "count": len(processes),
            "filter": filter_by_name or "all",
        })
    except Exception as e:
        logger.error("进程探针异常: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"探针执行异常: {e}")


# ---- 网络探针 ----

@router.get("/network", response_model=APIResponse, summary="网络状态")
async def probe_network(
    action: str = Query(default="connections", description="connections | interfaces | dns"),
    hostname: str | None = None,
) -> APIResponse:
    """
    网络信息探针。

    - connections: 当前网络连接（ss/netstat）
    - interfaces: 网络接口信息（ip addr）
    - dns: DNS 解析测试（需要 hostname 参数）
    """
    try:
        if action == "interfaces":
            result = await network_interfaces()
            items = [i.to_dict() if hasattr(i, "to_dict") else i for i in result]
            return APIResponse(data={"interfaces": items})

        elif action == "dns":
            if not hostname:
                raise HTTPException(status_code=422, detail="DNS 解析需要 hostname 参数")
            result = await dns_resolve(hostname=hostname)
            return APIResponse(data={"dns": result})

        else:  # connections (default)
            result = await network_connections()
            items = [c.to_dict() if hasattr(c, "to_dict") else c for c in result]
            return APIResponse(data={
                "connections": items,
                "count": len(items),
            })

    except HTTPException:
        raise
    except Exception as e:
        logger.error("网络探针异常: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"探针执行异常: {e}")


# ---- 日志探针 ----

@router.get("/logs", response_model=APIResponse, summary="系统日志")
async def probe_logs(
    since: str | None = Query(None, description="起始时间，如 '1 hour ago'"),
    until: str | None = Query(None, description="结束时间"),
    unit: str = Query(default="system", description="system | kernel | user"),
    grep: str | None = Query(None, description="关键词过滤"),
    lines: int = Query(default=100, ge=1, le=10000),
    tail_path: str | None = Query(None, description="指定文件 tail（替代 journalctl）"),
) -> APIResponse:
    """
    系统日志查询。

    默认使用 journalctl，可切换为 tail 文件模式或 grep 模式。
    所有操作只读，不修改日志文件。
    """
    try:
        if tail_path:
            # 文件 tail 模式
            entries = await tail_file(path=tail_path, lines=lines)
        elif grep:
            # grep 过滤模式
            entries = await grep_log(pattern=grep, unit=unit, lines=lines)
        else:
            # journalctl 模式
            entries = await journal_logs(since=since, until=until, unit=unit, lines=lines)

        result_list = []
        for entry in entries:
            if hasattr(entry, "to_dict"):
                result_list.append(entry.to_dict())
            elif isinstance(entry, dict):
                result_list.append(entry)
            else:
                result_list.append(str(entry))

        return APIResponse(data={
            "logs": result_list,
            "count": len(result_list),
            "mode": "tail" if tail_path else ("grep" if grep else "journalctl"),
        })
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"日志源不存在: {e}")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=f"读取权限不足: {e}")
    except Exception as e:
        logger.error("日志探针异常: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"探针执行异常: {e}")
