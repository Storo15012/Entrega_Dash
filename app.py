"""
Dash dashboard for electricity consumption and production in Romania.

This app is designed to be deployed on Render.com as a Python web service.
It reads a CSV file containing electricity consumption and production data,
and exposes several interactive graphs and a data table using Plotly Dash.

The code has been adapted from a Colab notebook version to work in a
deployment environment.  Key changes include:

* Loading the CSV from a relative path within the repository instead of
  an absolute `/content` path (Colab-specific).  By default the file
  ``electricityConsumptionAndProductioction.csv`` should be placed in the
  same directory as this script.  You can override the path by
  supplying an environment variable ``CSV_PATH`` if necessary.

* Defining ``server = app.server`` so that gunicorn can locate the WSGI
  application object when Render runs ``gunicorn app:server`` (or
  ``gunicorn my_app:server`` if you rename this file).  Gunicorn will
  import this module and expose the Flask server contained in your Dash
  instance.

* Avoiding debug mode for production.  When running locally you can
  execute this file directly (``python app.py``) and the application
  will start on http://127.0.0.1:8050.  In production on Render,
  gunicorn will start the server instead of executing the ``if
  __name__ == '__main__'`` block.

For deployment instructions see README.md and the ``render.yaml`` file.
"""

import os
from dash import Dash, html, dash_table, dcc, callback, Output, Input, ctx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import dash_bootstrap_components as dbc


# Determine the path to the CSV.  Use the CSV_PATH environment variable
# if set; otherwise default to a file in the same directory as this script.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV = os.path.join(BASE_DIR, "electricityConsumptionAndProductioction.csv")
CSV_PATH = os.environ.get("CSV_PATH", DEFAULT_CSV)

# Load the CSV into a DataFrame.  If the file is missing, an exception
# will be raised and logged in the Render deploy logs.
df = pd.read_csv(CSV_PATH)

# Parse the timestamp column and derive additional fields used for grouping.
df["DateTime"] = pd.to_datetime(df["DateTime"])
df = df.sort_values("DateTime").reset_index(drop=True)

df["MonthStart"] = df["DateTime"].dt.to_period("M").dt.start_time
df["Weekday"] = df["DateTime"].dt.day_name()
df["Hour"] = df["DateTime"].dt.hour
min_date = df["DateTime"].min().date()
max_date = df["DateTime"].max().date()

# Define the list of power sources expected in the CSV.  Only include
# those columns that actually exist in the data to avoid errors when
# selecting from missing columns.
SOURCES = ["Nuclear", "Wind", "Hydroelectric", "Oil and Gas", "Coal", "Solar", "Biomass"]
sources_avail = [s for s in SOURCES if s in df.columns]

# Build the options for the metric dropdown.  Use human‑friendly labels.
metric_options = []
if "Consumption" in df.columns:
    metric_options.append({"label": "Consumo", "value": "Consumption"})
if "Production" in df.columns:
    metric_options.append({"label": "Producción total", "value": "Production"})
if not metric_options:
    # fallback: if neither Consumption nor Production exists, list the
    # available source columns
    metric_options = [{"label": s, "value": s} for s in sources_avail]
default_metric = metric_options[0]["value"]

# Initialize the Dash app with a bootstrap theme.  Expose the Flask
# server object for gunicorn.  In production gunicorn will import this
# module and look for ``server``.
external_stylesheets = [dbc.themes.CERULEAN]
app = Dash(__name__, external_stylesheets=external_stylesheets)
server = app.server


# Layout definition
app.layout = dbc.Container([
    dbc.Row([
        html.Div('Electricidad – Consumo y Producción (Rumania)',
                 className="text-primary text-center fs-3 mt-3")
    ]),

    dbc.Row([
        dbc.Col([
            html.Label("Rango de fechas"),
            dcc.DatePickerRange(
                id="date-range",
                start_date=min_date, end_date=max_date,
                min_date_allowed=min_date, max_date_allowed=max_date,
                display_format="YYYY-MM-DD"
            )
        ], md=4),
        dbc.Col([
            html.Label("Métrica (Gráfico 1)"),
            dcc.Dropdown(
                id="metric-dropdown",
                options=metric_options,
                value=default_metric,
                clearable=False
            )
        ], md=4),
        dbc.Col([
            html.Label("Tema"),
            dbc.ButtonGroup([
                dbc.Button("Claro", id="btn-light", outline=True),
                dbc.Button("Oscuro", id="btn-dark", outline=True)
            ], className="d-block"),
            dcc.Store(id="theme-store", data={"template": "plotly"})
        ], md=4),
    ], className="my-2"),

    dbc.Row([
        dbc.Col([
            html.H5("1) Serie temporal con range slider y selector", className="text-primary"),
            dcc.Graph(id='graph-line')
        ], width=6),
        dbc.Col([
            html.H5("2) Producción por fuente", className="text-primary"),
            dbc.Row([
                dbc.Col([
                    html.Label("Fuentes"),
                    dcc.Checklist(
                        id="sources-checklist",
                        options=[{"label": s, "value": s} for s in sources_avail],
                        value=sources_avail[:4] if len(sources_avail) >= 4 else sources_avail,
                        inline=True,
                        inputStyle={"margin-right": "6px", "margin-left": "12px"}
                    )
                ], md=9),
                dbc.Col([
                    html.Label("Tipo gráfico"),
                    dbc.ButtonGroup([
                        dbc.Button("Área apilada", id="btn-area", outline=True, size="sm"),
                        dbc.Button("Líneas", id="btn-lines", outline=True, size="sm")
                    ])
                ], md=3)
            ]),
            dcc.Graph(id='graph-sources')
        ], width=6),
    ]),

    dbc.Row([
        dbc.Col([
            html.H5("3) Agregado mensual (barras)", className="text-primary"),
            dbc.Row([
                dbc.Col([
                    html.Label("Variable"),
                    dcc.Dropdown(
                        id="bar-var-dropdown",
                        options=metric_options + [{"label": s, "value": s} for s in sources_avail],
                        value=default_metric,
                        clearable=False
                    )
                ], md=7),
                dbc.Col([
                    html.Label("Agregación"),
                    dcc.RadioItems(
                        id="bar-agg-radio",
                        options=[
                            {"label": "Suma", "value": "sum"},
                            {"label": "Promedio", "value": "mean"},
                            {"label": "Máximo", "value": "max"}
                        ],
                        value="sum",
                        inline=True
                    )
                ], md=5)
            ]),
            dcc.Graph(id='graph-monthly-bar')
        ], width=6),
        dbc.Col([
            html.H5("4) Mapa de calor: hora × día (promedio)", className="text-primary"),
            html.Label("Variable"),
            dcc.Dropdown(
                id="heat-var-dropdown",
                options=metric_options + [{"label": s, "value": s} for s in sources_avail],
                value=default_metric,
                clearable=False
            ),
            dcc.Graph(id='graph-heatmap')
        ], width=6),
    ]),

    dbc.Row([
        dbc.Col([
            html.H5("Vista de datos (primeras 200 filas)", className="text-primary"),
            dash_table.DataTable(
                data=df.head(200).to_dict('records'),
                page_size=10,
                style_table={'overflowX': 'auto'},
                style_cell={"fontSize": 12, "fontFamily": "Arial"}
            )
        ])
    ], className="my-3")
], fluid=True)


# Theme switch callback
@callback(Output("theme-store", "data"),
          Input("btn-light", "n_clicks"), Input("btn-dark", "n_clicks"))
def switch_theme(n_light, n_dark):
    """Switch between light and dark Plotly templates."""
    trig = ctx.triggered_id
    return {"template": "plotly_dark"} if trig == "btn-dark" else {"template": "plotly"}


def _filter(dfin: pd.DataFrame, start, end) -> pd.DataFrame:
    """
    Filter the input DataFrame between the given start and end dates.

    Parameters
    ----------
    dfin : DataFrame
        The DataFrame to filter.
    start : str or datetime
        The start date (inclusive).
    end : str or datetime
        The end date (inclusive).

    Returns
    -------
    DataFrame
        A copy of the DataFrame filtered by the date range.
    """
    if start is None or end is None:
        return dfin
    return dfin[(dfin["DateTime"] >= pd.to_datetime(start)) &
                (dfin["DateTime"] <= pd.to_datetime(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))].copy()


# Callbacks to update each graph
@callback(Output('graph-line', 'figure'),
          Input('date-range', 'start_date'), Input('date-range', 'end_date'),
          Input('metric-dropdown', 'value'), Input('theme-store', 'data'))
def update_line(start_date, end_date, metric, theme):
    """Update the time series line chart based on selected metric and date range."""
    dff = _filter(df, start_date, end_date)
    fig = px.line(
        dff,
        x='DateTime', y=metric,
        template=theme["template"],
        title=f"Serie temporal de {metric}"
    )
    fig.update_xaxes(
        rangeslider=dict(visible=True),
        rangeselector=dict(buttons=[
            dict(count=1, label="1M", step="month", stepmode="backward"),
            dict(count=6, label="6M", step="month", stepmode="backward"),
            dict(count=1, label="1Y", step="year", stepmode="backward"),
            dict(step="all", label="Todo")
        ])
    )
    fig.update_layout(margin=dict(l=10, r=10, t=50, b=10))
    return fig


@callback(Output('graph-sources', 'figure'),
          Input('date-range', 'start_date'), Input('date-range', 'end_date'),
          Input('sources-checklist', 'value'),
          Input('btn-area', 'n_clicks'), Input('btn-lines', 'n_clicks'),
          Input('theme-store', 'data'))
def update_sources(start_date, end_date, sources_sel, n_area, n_lines, theme):
    """Update the production-by-source chart as either stacked area or lines."""
    dff = _filter(df, start_date, end_date)
    if not sources_sel:
        fig = go.Figure()
        fig.update_layout(title="Selecciona al menos una fuente", template=theme["template"])
        return fig
    view = "lines" if (n_lines or 0) > (n_area or 0) else "area"
    monthly = dff.set_index("DateTime")[sources_sel].resample("M").sum().reset_index()
    fig = (px.area if view == "area" else px.line)(
        monthly, x="DateTime", y=sources_sel,
        template=theme["template"],
        title=f"Producción por fuente (mensual, {'área apilada' if view == 'area' else 'líneas'})"
    )
    fig.update_layout(legend_title_text="Fuentes", margin=dict(l=10, r=10, t=50, b=10))
    return fig


@callback(Output('graph-monthly-bar', 'figure'),
          Input('date-range', 'start_date'), Input('date-range', 'end_date'),
          Input('bar-var-dropdown', 'value'), Input('bar-agg-radio', 'value'),
          Input('theme-store', 'data'))
def update_bar(start_date, end_date, var, agg, theme):
    """Update the monthly aggregate bar chart based on aggregation method."""
    dff = _filter(df, start_date, end_date)
    if agg == "sum":
        dfa, subtitle = dff.groupby("MonthStart", as_index=False)[var].sum(), "Suma mensual"
    elif agg == "mean":
        dfa, subtitle = dff.groupby("MonthStart", as_index=False)[var].mean(), "Promedio mensual"
    else:
        dfa, subtitle = dff.groupby("MonthStart", as_index=False)[var].max(), "Máximo mensual"
    fig = px.bar(
        dfa, x="MonthStart", y=var,
        template=theme["template"],
        title=f"{subtitle}: {var}"
    )
    fig.update_layout(xaxis_title="Mes", yaxis_title=var, margin=dict(l=10, r=10, t=50, b=10))
    return fig


@callback(Output('graph-heatmap', 'figure'),
          Input('date-range', 'start_date'), Input('date-range', 'end_date'),
          Input('heat-var-dropdown', 'value'), Input('theme-store', 'data'))
def update_heatmap(start_date, end_date, var, theme):
    """Update the heatmap representing average values by hour and weekday."""
    dff = _filter(df, start_date, end_date)
    pv = dff.pivot_table(index="Weekday", columns="Hour", values=var, aggfunc="mean")
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    pv = pv.reindex(order, axis=0, fill_value=0.0)
    fig = go.Figure(data=go.Heatmap(
        z=pv.values.astype(float),
        x=list(pv.columns), y=list(pv.index),
        colorbar_title=f"Prom {var}",
        hoverongaps=False
    ))
    fig.update_layout(
        title=f"Promedio por hora vs día: {var}",
        template=theme["template"],
        xaxis_title="Hora del día", yaxis_title="Día de la semana",
        margin=dict(l=10, r=10, t=50, b=10)
    )
    return fig


if __name__ == '__main__':
    # Run the Dash development server for local debugging.  In production,
    # Render will invoke gunicorn with the ``app:server`` WSGI entrypoint.
    app.run_server(host="0.0.0.0", port=8050, debug=False)
