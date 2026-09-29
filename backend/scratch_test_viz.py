import subprocess
import json

# Node script to simulate the frontend visualization pipeline
script = """
import { resolveVisualizationSpec } from './semanticClassifier.js';
import { getChartCompatibility } from './chartRecommender.js';
import { prepareChartData } from './echartsBuilder.js';

const result = {
    columns: ["country", "product", "product_revenue", "product_rank"],
    rows: [
        {country: "G4", product: "A", product_revenue: 500, product_rank: 1},
        {country: "G4", product: "B", product_revenue: 300, product_rank: 2},
        {country: "G4", product: "C", product_revenue: 200, product_rank: 3},
        {country: "G3", product: "D", product_revenue: 450, product_rank: 1},
        {country: "G3", product: "E", product_revenue: 350, product_rank: 2},
        {country: "G3", product: "F", product_revenue: 150, product_rank: 3},
        {country: "G2", product: "G", product_revenue: 400, product_rank: 1},
        {country: "G2", product: "H", product_revenue: 250, product_rank: 2},
        {country: "G2", product: "I", product_revenue: 100, product_rank: 3}
    ]
};

const intent = "ranking";
const query = "Rank countries by revenue, then show the top 3 products within each of the top 3 countries.";

try {
    const spec = resolveVisualizationSpec(result, intent, query, null);
    console.log("SPEC:", JSON.stringify(spec, null, 2));
    
    const semanticResult = {
        columns: [spec.dimension, spec.secondaryDimension, spec.primaryMeasure, ...(spec.secondaryMeasures || [])].filter(Boolean),
        rows: result.rows
    };
    
    const compat = getChartCompatibility(semanticResult, intent, query);
    console.log("COMPATIBILITY horizontalBar:", compat['horizontalBar']);
    
    const chartData = prepareChartData(semanticResult, spec);
    console.log("CHART DATA:", JSON.stringify(chartData, null, 2));
} catch (err) {
    console.error("ERROR:", err.message);
    console.error(err.stack);
}
"""

with open("d:/MAJOR PROJECT/voice_BI/frontend/src/utils/test_viz.js", "w") as f:
    f.write(script)

# Run it
try:
    # Need to run it as an ES module or bypass it. 
    pass
except Exception as e:
    pass
