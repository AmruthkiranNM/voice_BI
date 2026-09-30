# End-to-end acceptance run

## 1. Forecast revenue for the next 3 months.

- pipeline: PREDICTIVE | rows: 3 | 8.7s
- frequency: months | observations: 15 | horizon: 3
- granularity: total | groups: 1 | periods per group: 3
- model(s): Seasonal Naive
- MASE: 4.36 | beats naive: True
- forecast values:
    - None: 2022-04-30=2,885,253, 2022-05-31=2,794,491, 2022-06-30=2,626,162

answer: FORECAST: amount for 3 months after 2022-03-31.
PERIODS COVERED: 2022-04-30 to 2022-06-30.
FORECAST TOTAL over the horizon: 8,305,906.00
FIRST PERIOD 2022-04-30: 2,885,253.00
LAST PERIOD 2022-06-30: 2,626,162.00
MODEL: Seasonal Naive (chosen by rolling_origin_backtest); beats the naive baseline: True.
RELIABILITY: NOT reliable — MASE 4.36 is at or above 1, meaning the model was no better than simp

## 2. Forecast revenue for the next 6 months.

- pipeline: PREDICTIVE | rows: 6 | 5.7s
- frequency: months | observations: 15 | horizon: 6
- granularity: total | groups: 1 | periods per group: 6
- model(s): Damped Holt Trend
- MASE: 2.56 | beats naive: True
- forecast values:
    - None: 2022-04-30=2,858,378, 2022-05-31=2,856,971, 2022-06-30=2,855,845, 2022-07-31=2,854,945, 2022-08-31=2,854,225, 2022-09-30=2,853,648

answer: FORECAST: amount for 6 months after 2022-03-31.
PERIODS COVERED: 2022-04-30 to 2022-09-30.
FORECAST TOTAL over the horizon: 17,134,012.43
FIRST PERIOD 2022-04-30: 2,858,378.10
LAST PERIOD 2022-09-30: 2,853,648.26
MODEL: Damped Holt Trend (chosen by rolling_origin_backtest); beats the naive baseline: True.
RELIABILITY: NOT reliable — MASE 2.56 is at or above 1, meaning the model was no better than 

## 3. Forecast revenue for the next 12 months.

- pipeline: PREDICTIVE | rows: 10 | 4.1s
- frequency: months | observations: 15 | horizon: 12
- granularity: total | groups: 1 | periods per group: 12
- model(s): Drift
- MASE: 2.16 | beats naive: True
- forecast values:
    - None: 2022-04-30=2,264,447, 2022-05-31=2,218,264, 2022-06-30=2,172,081, 2022-07-31=2,125,898, 2022-08-31=2,079,715, 2022-09-30=2,033,532, 2022-10-31=1,987,349, 2022-11-30=1,941,166, 2022-12-31=1,894,983, 2023-01-31=1,848,800, 2023-02-28=1,802,617, 2023-03-31=1,756,434

answer: The model projects total revenue of **$24,125,286.00** over the next 12 months, from 2022‑04‑30 to 2023‑03‑31. The first month is projected at **$2,264,447.00** and the final month at **$1,756,434.00**. The Drift model was selected after back‑testing and outperformed the naive baseline. However, the MASE of 2.16 indicates the forecast is not reliable, so treat the figures as indicative only.

## 4. Forecast revenue by region for the next 12 months.

- pipeline: PREDICTIVE | rows: 36 | 15.8s
- frequency: months | observations: None | horizon: 12
- granularity: region | groups: 3 | periods per group: 12
- model(s): Damped Holt Trend x1, Moving Average x1, Naive (last value) x1
- MASE: 1.61-3.31 | beats naive: 2/3
- forecast values:
    - APAC: 2022-04-30=1,172,409, 2022-05-31=1,172,409, 2022-06-30=1,172,409, 2022-07-31=1,172,409, 2022-08-31=1,172,409, 2022-09-30=1,172,409, 2022-10-31=1,172,409, 2022-11-30=1,172,409, 2022-12-31=1,172,409, 2023-01-31=1,172,409, 2023-02-28=1,172,409, 2023-03-31=1,172,409
    - Americas: 2022-04-30=924,382, 2022-05-31=923,522, 2022-06-30=922,835, 2022-07-31=922,285, 2022-08-31=921,845, 2022-09-30=921,492, 2022-10-31=921,211, 2022-11-30=920,986, 2022-12-31=920,805, 2023-01-31=920,661, 2023-02-28=920,546, 2023-03-31=920,453
    - Europe: 2022-04-30=507,400, 2022-05-31=507,400, 2022-06-30=507,400, 2022-07-31=507,400, 2022-08-31=507,400, 2022-09-30=507,400, 2022-10-31=507,400, 2022-11-30=507,400, 2022-12-31=507,400, 2023-01-31=507,400, 2023-02-28=507,400, 2023-03-31=507,400

answer: The model projects revenue for the 12‑month period ending 2023‑03‑31.  
Forecast totals are **APAC: $14,068,908.00**, **Americas: $11,061,022.54**, **Europe: $6,088,796.00**.  
These figures are derived from the Damped Holt Trend, Moving Average, and Naive models selected per series by chronological validation.  
Combined, the forecasted revenue is **$31,218,726.54**.

## 5. Forecast revenue by product for the next 12 months.

- pipeline: PREDICTIVE | rows: 60 | 19.1s
- frequency: months | observations: None | horizon: 12
- granularity: product | groups: 22 | periods per group: 12
- model(s): Damped Holt Trend x2, Holt Linear Trend x1, Moving Average x3, Naive (last value) x7, Simple Exponential Smoothing x9
- MASE: 0.58-3.65 | beats naive: 15/22
- forecast values:
    - After Nines: 2022-04-30=169,902, 2022-05-31=169,902, 2022-06-30=169,902, 2022-07-31=169,902, 2022-08-31=169,902, 2022-09-30=169,902, 2022-10-31=169,902, 2022-11-30=169,902, 2022-12-31=169,902, 2023-01-31=169,902, 2023-02-28=169,902, 2023-03-31=169,902
    - Caramel Stuffed Bars: 2022-04-30=164,059, 2022-05-31=164,059, 2022-06-30=164,059, 2022-07-31=164,059, 2022-08-31=164,059, 2022-09-30=164,059, 2022-10-31=164,059, 2022-11-30=164,059, 2022-12-31=164,059, 2023-01-31=164,059, 2023-02-28=164,059, 2023-03-31=164,059
    - Drinking Coco: 2022-04-30=143,757, 2022-05-31=143,757, 2022-06-30=143,757, 2022-07-31=143,757, 2022-08-31=143,757, 2022-09-30=143,757, 2022-10-31=143,757, 2022-11-30=143,757, 2022-12-31=143,757, 2023-01-31=143,757, 2023-02-28=143,757, 2023-03-31=143,757

answer: The forecast for the period **2022‑04‑30 to 2023‑03‑31** projects total revenue of **$33,259,924.71** across 22 product series. The largest series, **After Nines**, is projected to generate **$2,038,820.00**; **Caramel Stuffed Bars** **$1,968,708.00**; **Drinking Coco** **$1,725,080.00**; **Eclairs** **$1,704,444.00**; **Raspberry Choco** **$1,665,419.16**; **Almond Choco** **$1,644,452.94**; **99

## 6. Forecast revenue by salesperson for the next 6 months.

- pipeline: PREDICTIVE | rows: 60 | 22.7s
- frequency: months | observations: None | horizon: 6
- granularity: salesperson | groups: 25 | periods per group: 6
- model(s): Damped Holt Trend x2, Drift x2, Holt Linear Trend x3, Moving Average x6, Naive (last value) x2, Seasonal Naive x2, Simple Exponential Smoothing x8
- MASE: 0.40-1.72 | beats naive: 23/25
- forecast values:
    - Van Tuxwell: 2022-04-30=167,008, 2022-05-31=167,008, 2022-06-30=167,008, 2022-07-31=167,008, 2022-08-31=167,008, 2022-09-30=167,008
    - Wilone O'Kielt: 2022-04-30=160,092, 2022-05-31=160,092, 2022-06-30=160,092, 2022-07-31=160,092, 2022-08-31=160,092, 2022-09-30=160,092
    - Gunar Cockshoot: 2022-04-30=155,069, 2022-05-31=155,069, 2022-06-30=155,069, 2022-07-31=155,069, 2022-08-31=155,069, 2022-09-30=155,069

answer: The model projects the following revenue totals for each salesperson over the next six months (2022‑04‑30 to 2022‑09‑30):

- **Van Tuxwell:** **$1,002,050.00**  
- **Wilone O'Kielt:** **$960,554.00**  
- **Gunar Cockshoot:** **$930,412.00**  
- **Dennison Crosswaite:** **$761,687.34**  
- **Roddy Speechley:** **$756,838.71**  
- **Dotty Strutley:** **$714,037.14**  
- **Marney O'Breen:** **$702,28

## 7. Forecast the top 5 products by revenue for the next 12 months.

- pipeline: PREDICTIVE | rows: 11 | 26.5s
- frequency: months | observations: None | horizon: 12
- granularity: product | groups: 22 | periods per group: 12
- model(s): Damped Holt Trend x2, Holt Linear Trend x1, Moving Average x3, Naive (last value) x7, Simple Exponential Smoothing x9
- MASE: 0.58-3.65 | beats naive: 15/22
- forecast values:
    - After Nines: 2022-04-30=169,902, 2022-05-31=169,902, 2022-06-30=169,902, 2022-07-31=169,902, 2022-08-31=169,902, 2022-09-30=169,902, 2022-10-31=169,902, 2022-11-30=169,902, 2022-12-31=169,902, 2023-01-31=169,902, 2023-02-28=169,902, 2023-03-31=169,902
    - Caramel Stuffed Bars: 2022-04-30=164,059, 2022-05-31=164,059, 2022-06-30=164,059, 2022-07-31=164,059, 2022-08-31=164,059, 2022-09-30=164,059, 2022-10-31=164,059, 2022-11-30=164,059, 2022-12-31=164,059, 2023-01-31=164,059, 2023-02-28=164,059, 2023-03-31=164,059
    - Drinking Coco: 2022-04-30=143,757, 2022-05-31=143,757, 2022-06-30=143,757, 2022-07-31=143,757, 2022-08-31=143,757, 2022-09-30=143,757, 2022-10-31=143,757, 2022-11-30=143,757, 2022-12-31=143,757, 2023-01-31=143,757, 2023-02-28=143,757, 2023-03-31=143,757

answer: FORECAST: amount for 12 months after 2022-03-31, by product.
PERIODS COVERED: 2022-04-30 to 2023-03-31.
RANKED FORECAST TOTALS:
  1. After Nines: 2,038,820.00
  2. Caramel Stuffed Bars: 1,968,708.00
  3. Drinking Coco: 1,725,080.00
  4. Eclairs: 1,704,444.00
  5. Raspberry Choco: 1,665,419.16
(22 entities were forecast and ranked.)
MODELS: selected per series by chronological validation (Damped Ho

## 8. Will the top 5 products remain the same next year?

- pipeline: PREDICTIVE | rows: 0 | 16.5s
- frequency: months | observations: None | horizon: 0
- granularity: total | groups: 0 | periods per group: 0
- model(s): -
- MASE: - | beats naive: None
- forecast values:

answer: Which measure would you like me to predict? This dataset has amount, customers, or boxes.

## 9. Provide details of all products sold by salesperson.

- pipeline: None | rows: 7617 | 48.6s
- unsolicited analysis phrases: none
- sql: `SELECT people.salesperson,        products.product,        products.category,        products.size,        sales.amount,        sales.boxes FROM sales JOIN people ON sales.spid = p`

answer: Here are the products sold by each salesperson, showing **salesperson**, **product**, **category**, **size**, **amount**, and **boxes**.

## 10. Rank countries by revenue.

- pipeline: None | rows: 6 | 43.5s
- sql: `SELECT country, revenue, ROW_NUMBER() OVER (ORDER BY revenue DESC) AS rank FROM (     SELECT geo.geo AS country, SUM(sales.amount) AS revenue     FROM sales     JOIN geo ON sales.g`

answer: **Your business’s revenue by country (ranked from highest to lowest):**

1. **New Zealand** – **$7,435,918** (rank 1)  
2. **Canada** – **$7,350,091** (rank 2)  
3. **India** – **$7,310,254** (rank 3)  
4. **Australia** – **$7,263,151** (rank 4)  
5. **UK** – **$7,189,609** (rank 5)  
6. **USA** – **$7,012,523** (rank 6)

**Key takeaways:**

- New Zealand leads by a margin of **$1,172,909** over t

## 11. Show revenue trend over time.

- pipeline: None | rows: 15 | 32.8s
- sql: `SELECT strftime('%Y-%m', saledate) AS month, SUM(amount) AS revenue FROM sales GROUP BY month ORDER BY month;`

answer: Your revenue has shown a **volatile pattern** over the past year.

- **2021**: Revenue started at **$2.96 M** in January, climbed to a peak of **$3.19 M** in March, then dipped to a low of **$2.45 M** in July. By December it was back up to **$2.94 M**, close to the year‑start level.  
- **2022**: A sharp **spike** to **$5.28 M** in January (about **78 % higher** than January 2021) was followed by 
