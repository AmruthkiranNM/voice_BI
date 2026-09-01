export const STAGE_TYPES = {
  UNDERSTANDING: 'Understanding Question',
  INTENT: 'Detecting Business Intent',
  CONTEXT: 'Retrieving Conversation Memory',
  SCHEMA: 'Analyzing Database Schema',
  TABLES: 'Identifying Relevant Tables',
  METRICS: 'Selecting Business Metrics',
  SQL_GEN: 'Generating Optimized SQL',
  VALIDATION: 'Validating SQL Query',
  EXECUTION: 'Executing Database Query',
  ANALYZING_RESULTS: 'Analyzing Returned Results',
  TRENDS: 'Detecting Trends',
  INSIGHTS: 'Generating Business Insights',
  VISUALIZATION_SELECT: 'Selecting Best Visualization',
  PREPARING_CHARTS: 'Preparing Charts',
  EXECUTIVE_EXPLANATION: 'Generating Executive Explanation',
  FINALIZING: 'Finalizing Response'
};

const ALL_STAGES = [
  STAGE_TYPES.UNDERSTANDING,
  STAGE_TYPES.INTENT,
  STAGE_TYPES.CONTEXT,
  STAGE_TYPES.SCHEMA,
  STAGE_TYPES.TABLES,
  STAGE_TYPES.METRICS,
  STAGE_TYPES.SQL_GEN,
  STAGE_TYPES.VALIDATION,
  STAGE_TYPES.EXECUTION,
  STAGE_TYPES.ANALYZING_RESULTS,
  STAGE_TYPES.TRENDS,
  STAGE_TYPES.INSIGHTS,
  STAGE_TYPES.VISUALIZATION_SELECT,
  STAGE_TYPES.PREPARING_CHARTS,
  STAGE_TYPES.EXECUTIVE_EXPLANATION,
  STAGE_TYPES.FINALIZING
];

// Determine complexity based on keywords and length
export function analyzeComplexity(query) {
  const q = query.toLowerCase();
  const wordCount = query.split(/\s+/).length;

  const hasAggregation = /(sum|total|average|avg|count|min|max)/.test(q);
  const hasComparison = /(compare|versus|vs|difference|between|than)/.test(q);
  const hasTrend = /(trend|growth|over time|history|historical)/.test(q);
  const hasForecast = /(forecast|predict|next month|future|expect)/.test(q);
  const hasGrouping = /(by|group|each|per)/.test(q);
  const hasRanking = /(top|bottom|best|worst|highest|lowest|fastest)/.test(q);

  let score = 0;
  if (wordCount > 10) score += 1;
  if (wordCount > 20) score += 2;

  if (hasAggregation) score += 1;
  if (hasComparison) score += 2;
  if (hasTrend) score += 2;
  if (hasForecast) score += 3;
  if (hasGrouping) score += 1;
  if (hasRanking) score += 1;

  if (score >= 6 || hasForecast) {
    return { level: 'hard', targetDurationMs: 50 }; // 50ms
  } else if (score >= 3 || hasComparison || hasTrend) {
    return { level: 'medium', targetDurationMs: 45 }; // 45ms
  } else {
    return { level: 'simple', targetDurationMs: 40 }; // 40ms
  }
}

// Generate the specific pipeline for this query
export function generatePipeline(complexityLevel, targetDurationMs) {
  let selectedStages = [];

  if (complexityLevel === 'simple') {
    selectedStages = [
      STAGE_TYPES.UNDERSTANDING,
      STAGE_TYPES.SCHEMA,
      STAGE_TYPES.SQL_GEN,
      STAGE_TYPES.EXECUTION,
      STAGE_TYPES.FINALIZING
    ];
  } else if (complexityLevel === 'medium') {
    selectedStages = [
      STAGE_TYPES.UNDERSTANDING,
      STAGE_TYPES.INTENT,
      STAGE_TYPES.SCHEMA,
      STAGE_TYPES.TABLES,
      STAGE_TYPES.METRICS,
      STAGE_TYPES.SQL_GEN,
      STAGE_TYPES.EXECUTION,
      STAGE_TYPES.VISUALIZATION_SELECT,
      STAGE_TYPES.PREPARING_CHARTS,
      STAGE_TYPES.FINALIZING
    ];
  } else {
    selectedStages = [...ALL_STAGES];
  }

  // Allocate durations so they sum exactly to targetDurationMs
  // We'll give slightly more time to execution and generation stages
  const baseWeights = selectedStages.map(stage => {
    if (stage === STAGE_TYPES.SQL_GEN || stage === STAGE_TYPES.EXECUTIVE_EXPLANATION) return 1.5;
    if (stage === STAGE_TYPES.EXECUTION || stage === STAGE_TYPES.SCHEMA || stage === STAGE_TYPES.PREPARING_CHARTS) return 1.2;
    if (stage === STAGE_TYPES.FINALIZING) return 0.5;
    return 1.0;
  });

  const totalWeight = baseWeights.reduce((a, b) => a + b, 0);

  const pipeline = selectedStages.map((stageName, index) => {
    const weight = baseWeights[index];
    const durationMs = Math.floor((weight / totalWeight) * targetDurationMs);
    return {
      id: `stage-${index}`,
      name: stageName,
      durationMs,
    };
  });

  // Adjust last item to account for rounding errors
  const currentTotal = pipeline.reduce((sum, stage) => sum + stage.durationMs, 0);
  const diff = targetDurationMs - currentTotal;
  if (diff !== 0 && pipeline.length > 0) {
    pipeline[pipeline.length - 1].durationMs += diff;
  }

  return pipeline;
}

export const LOADING_MESSAGES = [
  "Analyzing sales relationships...",
  "Finding top-performing products...",
  "Computing revenue trends...",
  "Comparing historical performance...",
  "Evaluating customer behavior...",
  "Optimizing SQL execution...",
  "Preparing executive summary...",
  "Detecting anomalies...",
  "Building visualization...",
  "Generating business explanation...",
  "Scanning table indexes...",
  "Aligning semantic context...",
  "Refining aggregation logic..."
];

export function getRandomMessage() {
  return LOADING_MESSAGES[Math.floor(Math.random() * LOADING_MESSAGES.length)];
}
