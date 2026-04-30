/**
 * XSS 防护工具函数
 *
 * 对用户输入的内容进行 HTML 转义，防止 XSS 攻击。
 * 使用场景：命令字符串、日志内容、错误消息等直接渲染到 DOM 的文本。
 */

/**
 * 转义 HTML 特殊字符，防止 XSS 注入
 * @param {string} str - 需要转义的原始字符串
 * @returns {string} 转义后的安全字符串
 */
export function escapeHtml(str) {
  if (str === null || str === undefined) return ''
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;')
}
