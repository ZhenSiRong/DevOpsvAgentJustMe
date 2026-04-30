import { useState, useRef, useEffect, useCallback } from 'react'

/**
 * 轻量级虚拟滚动 Hook
 *
 * 用于大列表渲染优化，只渲染可视区域内的行。
 * 无需额外依赖（react-virtualized / react-window / @tanstack/react-virtual）。
 *
 * 使用方式：
 *   const { containerRef, visibleItems, totalHeight, onScroll }
 *     = useVirtualScroll(data, { rowHeight: 36, overscan: 5 })
 *
 *   <div ref={containerRef} onScroll={onScroll} style={{ height: 400, overflowY: 'auto' }}>
 *     <div style={{ height: totalHeight }}>
 *       {visibleItems.map(item => (
 *         <div style={{ position: 'absolute', top: item.offset, height: rowHeight }}>
 *           {item.data.name}
 *         </div>
 *       ))}
 *     </div>
 *   </div>
 */

export function useVirtualScroll(items, options = {}) {
  const {
    rowHeight = 36,
    overscan = 5,
    containerHeight = 400,
  } = options

  const containerRef = useRef(null)
  const [scrollTop, setScrollTop] = useState(0)

  const totalHeight = items.length * rowHeight

  // 计算可见范围
  const startIndex = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan)
  const visibleCount = Math.ceil(containerHeight / rowHeight) + overscan * 2
  const endIndex = Math.min(items.length, startIndex + visibleCount)

  const visibleItems = items.slice(startIndex, endIndex).map((item, i) => ({
    data: item,
    offset: (startIndex + i) * rowHeight,
    index: startIndex + i,
  }))

  const onScroll = useCallback((e) => {
    setScrollTop(e.target.scrollTop)
  }, [])

  return {
    containerRef,
    visibleItems,
    totalHeight,
    onScroll,
    startIndex,
    endIndex,
    totalCount: items.length,
  }
}

export default useVirtualScroll
