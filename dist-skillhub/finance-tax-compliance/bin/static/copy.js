/* ==========================================================================
   copy.js — 统一文案字典（v6.0）
   目标：消除同一状态在不同位置的表述差异；所有新增 UI 文本从此字典取值。
   约定：术语统一用「知识库条目 / 法规依据 / 风险与合规提示 / 深度解读」，
        不再混用「原文 / 条款 / 提示 / 详细分析」等口语别名。
   ========================================================================== */
window.COPY = {
  app: "财税合规智能体",
  mode: {
    standard: "标准答复",
    deep: "深度解读",
    standardHint: "结论 → 依据 → 风险与合规提示",
    deepHint: "定义 → 辨析 → 因果 → 适用条件 → 易混淆 → 局限，每段附法规依据",
    switched: (name) => `已切换为「${name}」`,
  },
  stages: [
    { key: "triage", label: "意图分诊" },
    { key: "retrieve", label: "检索知识库" },
    { key: "compose", label: "角色精编" },
    { key: "verify", label: "引用校验" },
    { key: "audit", label: "合规复核" },
  ],
  progress: {
    start: "正在检索知识库…",
    streaming: "正在生成回答…",
    deep: "正在组织深度解读…",
    done: "回答已完成",
    stopped: "已停止生成",
  },
  empty: {
    chat: "还没有提问。描述一个财税合规问题，或从下方示例开始。",
    search: "没有匹配的知识库条目。可以换个说法、按文号检索，或浏览分类。",
    concepts: "没有匹配的概念卡。试试「进项」「广宣费」「首违不罚」。",
    refs: "本条回答未附法规条目",
    followup: "暂无更多建议问题",
  },
  error: {
    context: "获取知识库上下文失败，已转本地检索",
    local: "本地检索失败",
    cloud: "云端模型不可用，已回退本地知识库答案",
    retry: "重试",
    switchModel: "切换模型",
    viewLocal: "查看本地答案",
    detail: "查看错误详情",
    offline: "网络连接已断开，回答将使用本地知识库",
    online: "网络已恢复",
  },
  action: {
    copy: "复制",
    regen: "重新生成",
    refs: "查看依据",
    deep: "展开深度解读",
    concepts: "概念解读面板",
    followup: "继续追问",
    clearFilter: "清空筛选",
    browseAll: "浏览全部分类",
    export: "导出 CSV",
  },
  label: {
    evidence: "证据链（本轮引用的知识库条目）",
    deepBlock: "知识深度解读",
    deepSections: "六段式解读",
    boundaries: "边界条件与数字门槛",
    scenarios: "常见场景判断路径",
    confusions: "易混淆对照",
    suggestions: "关联概念",
    warnings: "解读限制",
    tier: (t) => ({ A: "A 生产级 · 双源核验", B1: "B1 单源 · 元数据齐备", B2: "B2 参考层 · 引用前复核" }[t] || "未分层"),
    statusHint: (s) => s === "汇编·动态"
      ? "解释性条目，不是单一法规，不得据此判断法规效力"
      : "状态来自最近一次官方信源核验",
  },
  disclaimer: "回答基于知识库（核验日期 2026-11-07）生成，仅供合规参考，不构成税务师/律师专业意见；正式用途请以官方原文为准。",
  a11y: {
    skip: "跳到主内容",
    modeGroup: "回答模式",
    conceptDialog: "概念解读面板",
    conceptList: "概念列表",
    conceptDetail: "概念详情",
    progress: "回答生成进度",
    newAnswer: "新回答已生成",
  },
};
