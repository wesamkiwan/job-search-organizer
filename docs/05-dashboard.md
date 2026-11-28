# 5. Dashboard & analytics

Goal: show at a glance how the job search is going, and reveal **what works**, so the
strategy can be improved continuously.

## Dynamic behavior

- **Global filter bar:** date range (presets: last 7/30/90 days, this month, all
  time, custom), comparison with the previous period, and filters by source, channel,
  tag, remote type, employment type, and any choice-type custom field.
- **Customizable layout:** add, remove, reorder and resize widgets (drag and drop);
  the layout is saved in `DashboardLayout`. Multiple dashboards are possible later.
- **Drill-down:** clicking a chart segment or KPI opens the filtered application list
  behind it.
- **Custom fields become available automatically:** choice fields can be used as
  "group by" dimensions, number/money fields as measures.
- **Live updates:** widgets refresh via HTMX when filters change; no page reload.

## KPIs (tiles with trend vs. previous period)

| KPI | Definition |
|---|---|
| Applications sent | count with `applied_at` in period |
| Weekly goal progress | applications this week ÷ goal |
| Active pipeline | open applications (category `applied` / `in_progress` / `offer`) |
| Response rate | applications with any employer response (non-`applied` stage or response event) ÷ applications sent |
| Interview rate | applications reaching an interview stage ÷ applications sent |
| Offer rate | offers ÷ applications sent |
| Rejection rate / Ghosting rate | rejected ÷ sent; no response after N days (setting) ÷ sent |
| Avg. time to first response | days from applied to first employer reaction |
| Avg. time to offer | days from applied to offer |
| Follow-ups due | open tasks / `follow_up_on` ≤ today |
| Upcoming interviews | next 7 days |
| Inbox backlog | untriaged postings |

## Charts

| Chart | Type | Question it answers |
|---|---|---|
| Application funnel | funnel | Where do applications drop off? |
| Applications over time | bar (per week) + goal line | Am I consistent? |
| Responses & interviews over time | line | Is it improving? |
| Pipeline by stage | stacked bar / kanban counts | What's currently in flight? |
| Outcomes | donut | How do applications end? |
| Performance by source | grouped bar (sent, response %, interview %) | Which sources bring real opportunities? |
| Performance by channel | grouped bar | Portal vs. email vs. referral vs. recruiter? |
| **Performance by document version** | table + bar | Which CV / cover letter version gets more responses? (A/B comparison) |
| Rejection by stage & reason | stacked bar | Do I fail at screening or interviews? |
| Time in stage | box plot / bar | Where does the process stall? |
| Activity calendar | heatmap | When am I active? |
| Applications by weekday | bar | Does the day of applying matter? |
| Salary overview | histogram / range plot | Offered ranges vs. my expectation |
| By remote type / employment type / seniority / location | bar | Which job profiles respond best? |
| Interview performance | scatter (self-rating vs. outcome) | Do I judge my interviews correctly? |
| Source health | table | Postings found, new, duplicates, errors per source run |

## Insights panel

Rule-based observations computed from the data, e.g.:

- "Referral applications have a 3× higher interview rate than portal applications."
- "CV version 4 has a 28% response rate vs. 12% for version 3."
- "12 applications have had no response for 30+ days. Follow up or mark as ghosted?"
- "You are 4 applications behind this week's goal."

Insights only appear when there's enough data (minimum sample sizes), to avoid
misleading conclusions. Later, the AI module can add richer insights in this panel.

## Data quality requirements

The analytics are only as good as the tracking. The app supports this by:

- recording every stage change as a dated event (backdating allowed),
- asking for the rejection stage/reason when an application is closed as rejected,
- linking document versions when an application is created,
- suggesting "ghosted" automatically after N days without a response.

## Technical design

- `analytics/metrics.py`: registry of metric functions `(FilterContext) -> MetricResult`,
  built on selectors; unit tested with factory data.
- `analytics/widgets.py`: registry of widgets (metric + chart type + default size + options).
- Charts are server-rendered HTML styled with chart design tokens (light/dark), see ADR 0007.
- Aggregations happen in the database (Django ORM aggregation); results are cached per
  filter context and invalidated on relevant writes.
- Export: any widget's data as CSV; chart as PNG.
