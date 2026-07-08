/**
 * semanticClassifier.js
 * 
 * General, data-aware, query-aware semantic visualization decision engine.
 * Assigns semantic roles to columns instead of treating all numeric columns as measures.
 */

import { recommendChartType } from './chartRecommender';

// Helper: Normalize names for regex matching
const normalize = (s) => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');

const ID_PATTERNS = /^(id|key|code|uuid|guid|ref|reference|index|row|no|number)$|id$|_id$|^id_|key$/i;
const MEASURE_PATTERNS = /amount|revenue|sales|profit|salary|wage|cost|price|income|earning|spend|fee|budget|qty|quantity|count|total|sum|avg|min|max|rate|percent|pct|margin/i;
const DATE_PATTERNS = /date|month|year|week|quarter|period|time|day|timestamp/i;
const DATE_FORMAT = /^\d{4}[-/]\d{1,2}([-/]\d{1,2})?$|^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/i;

/**
 * Profiles all columns and assigns scores.
 */
export function classifyColumns(result, intent = '', query = '') {
  const { columns = [], rows = [] } = result || {};
  if (!columns.length || !rows.length) return [];

  const rowCount = rows.length;
  const qNorm = query.toLowerCase();
  
  return columns.map(col => {
    let type = 'string';
    let uniqueValues = new Set();
    let isNumeric = true;
    let isDate = false;
    let nullCount = 0;
    
    rows.forEach(r => {
      const v = r[col];
      uniqueValues.add(v);
      if (v == null || v === '') {
        nullCount++;
      } else {
        if (Number.isNaN(Number(v))) isNumeric = false;
        if (DATE_FORMAT.test(String(v))) isDate = true;
      }
    });

    if (isNumeric && rows.some(r => r[col] != null && r[col] !== '')) type = 'numeric';
    else if (isDate) type = 'date';

    const uniqueCount = uniqueValues.size;
    const uniqueness = uniqueCount / rowCount;
    
    let identifierScore = 0;
    let measureScore = 0;
    let dimensionScore = 0;
    let temporalScore = 0;

    const colNorm = normalize(col);
    const colRaw = String(col).toLowerCase();

    // 1. Evaluate Identifier Score
    if (ID_PATTERNS.test(colNorm) || ID_PATTERNS.test(colRaw)) {
      identifierScore += 0.6;
    }
    // High uniqueness in a non-single-row result often indicates an ID
    if (rowCount > 1 && uniqueness > 0.9 && type === 'numeric') {
      identifierScore += 0.3;
    }
    // If it's literally named "id"
    if (colNorm === 'id') identifierScore += 0.5;

    // 2. Evaluate Measure Score
    if (type === 'numeric') {
      measureScore += 0.4;
      if (MEASURE_PATTERNS.test(colNorm)) measureScore += 0.4;
      
      // Check if metric was explicitly requested in the query
      // Split column name into words and check if they exist in query
      const words = colRaw.split(/[_ ]/);
      const matchedWords = words.filter(w => w.length > 2 && qNorm.includes(w));
      if (matchedWords.length > 0) {
        measureScore += 0.3 * (matchedWords.length / words.length);
      }
      
      // If it looks like a year (e.g. 2023), don't score as measure
      if (uniqueValues.size > 0 && Array.from(uniqueValues).every(v => {
        const num = Number(v);
        return num > 1900 && num < 2100 && Number.isInteger(num);
      })) {
        measureScore -= 0.8;
      }

      // If it's definitely an ID, penalize measure score heavily
      if (identifierScore > 0.5) {
        measureScore -= 1.0;
      }
    }

    // 3. Evaluate Dimension Score
    if (type === 'string') {
      dimensionScore += 0.8;
    } else if (type === 'date' || DATE_PATTERNS.test(colRaw)) {
      dimensionScore += 0.5;
      temporalScore += 0.9;
    } else if (type === 'numeric' && identifierScore > 0.5) {
      dimensionScore += 0.3; // Fallback dimension
    }

    // Explicit mentions in query boost dimension score
    if (qNorm.includes(colNorm) && type === 'string') {
      dimensionScore += 0.3;
    }

    return {
      column: col,
      type,
      uniqueness,
      identifierScore,
      measureScore,
      dimensionScore,
      temporalScore,
    };
  });
}

/**
 * Resolves the primary visualization specification.
 */
export function resolveVisualizationSpec(result, intent = '', query = '') {
  if (!result || !result.columns || !result.rows || result.rows.length === 0) {
    return null;
  }

  const columnsProfile = classifyColumns(result, intent, query);
  
  // 1. Identify primary dimension
  let primaryDimension = null;
  
  // Sort by dimension score
  const potentialDimensions = [...columnsProfile].sort((a, b) => b.dimensionScore - a.dimensionScore);
  
  // Prefer a string or date dimension
  primaryDimension = potentialDimensions.find(c => c.type === 'string' || c.temporalScore > 0.5);
  
  // Fallback to identifier if absolutely no strings or dates exist
  if (!primaryDimension) {
    primaryDimension = potentialDimensions.find(c => c.identifierScore > 0.5);
  }
  // Absolute fallback to first column
  if (!primaryDimension) {
    primaryDimension = columnsProfile[0];
  }

  // 2. Identify primary measure
  let primaryMeasure = null;
  let secondaryMeasures = [];
  let excludedFields = [];
  
  const potentialMeasures = columnsProfile
    .filter(c => c.measureScore > 0)
    .sort((a, b) => b.measureScore - a.measureScore);

  if (potentialMeasures.length > 0) {
    primaryMeasure = potentialMeasures[0];
    secondaryMeasures = potentialMeasures.slice(1);
  }

  // Identify excluded fields (e.g. identifiers that shouldn't be plotted)
  columnsProfile.forEach(c => {
    if (c.identifierScore >= 0.6 && c.column !== primaryDimension.column) {
      excludedFields.push(c);
    }
  });

  // Remove excluded fields from secondary measures
  secondaryMeasures = secondaryMeasures.filter(sm => !excludedFields.some(ef => ef.column === sm.column));
  
  // Also, we don't want the dimension to be a measure
  secondaryMeasures = secondaryMeasures.filter(sm => sm.column !== primaryDimension.column);
  if (primaryMeasure && primaryMeasure.column === primaryDimension.column) {
    primaryMeasure = secondaryMeasures.shift() || null;
  }

  // Determine intent / chart
  // Use the existing logic but override with our clean semantic mappings
  // Create a mock "result" for chartRecommender that only includes the semantic columns
  const semanticColumns = [];
  if (primaryDimension) semanticColumns.push(primaryDimension.column);
  if (primaryMeasure) semanticColumns.push(primaryMeasure.column);
  secondaryMeasures.forEach(sm => semanticColumns.push(sm.column));

  const mockResult = {
    columns: semanticColumns,
    rows: result.rows
  };

  const chartRec = recommendChartType(mockResult, intent, query);

  const spec = {
    intent: intent || 'auto',
    dimension: primaryDimension?.column,
    primaryMeasure: primaryMeasure?.column,
    secondaryMeasures: secondaryMeasures.map(m => m.column),
    excludedFields: excludedFields.map(m => m.column),
    recommendedChart: chartRec.type,
    columnsProfile,
  };

  console.log('--- VISUALIZATION DECISION ENGINE ---');
  console.log('Query:', query);
  console.log('Intent:', intent);
  console.log('Dimension:', spec.dimension);
  console.log('Primary Measure:', spec.primaryMeasure);
  console.log('Excluded (IDs):', spec.excludedFields);
  console.log('Recommended Chart:', spec.recommendedChart);
  console.log('Profiles:', columnsProfile);
  console.log('---------------------------------------');

  return spec;
}
