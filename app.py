import os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from dash import Dash, html, dash_table, dcc, callback, Output, Input, ctx
import dash_bootstrap_components as dbc


# ========== Carga de datos ==========

CSV_PATH = os.environ.get("DATA_PATH", "electricity.csv")

if not os.path.exists(CSV_PATH):
    raise FileNotFoundError(
        f"No se encontró el archivo {CSV_PATH}. "
        f"Sube electricity.csv a tu repo o define DATA_PATH en Render."
    )

df = pd.read_csv(CSV_PATH)

# Validación básica
if "DateTime" not in df.columns:
    raise ValueError("El CSV debe contener una columna 'DateTime'.")

df["DateTime"] = pd.to_datetime(df["DateTime"])
df = df.sort_values("DateTime").reset_index(drop=True)

df["MonthStart"] = df["DateTime"].dt.to_period("M").dt.start_time
df["Weekday"] = df["DateTime"].dt.day_name()
df["Hour"] = df["DateTime"].dt.hour

min_date = df["DateTime"].min().date()
max_date = df["DateTime"].max().date()

SOURCES = ["Nuclear","Wind","Hydroelectric","Oil and Gas","Coal","Solar","Biomass"]
sources_avail = [s for s in SOURCES if s in df.columns]

metric_options = []
if "Consumption" in df.columns:
    metric_options.append({"label":"Consumo","value":"Consumption"})
if "Production" in df.columns:
    metric_options.append({"label":"Producción total","value":"Production"})
if not metric_options:
    metric_options = [{"label":s,"value":s} for s in sources_avail]

default_metric = metric_options[0]["value"]


# ========== Configuración DASH ==========

external_stylesheets = [dbc.themes.CERULEAN]
app = Dash(__name__, external_stylesheets=external_stylesheets)
server = app.server


# ========== Layout UI ==========

app.layout = dbc.Container([
    dbc.Row([html.Div("Electricidad – Consumo y Producción (Rumania)", 
                      className="text-primary text-center fs-3 mt-3")]),

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
            html.Label("Métrica"),
            dcc.Dropdown(id="metric-dropdown", options=metric_options,
                         value=default_metric, clearable=False)
        ], md=4),

        dbc.Col([
            html.Label("Tema"),
            dbc.ButtonGroup([
                dbc.Button("Claro", id="btn-light", outline=True),
                dbc.Button("Oscuro", id="btn-dark", outline=True)
            ]),
            dcc.Store(id="theme-store", data={"template":"plotly"})
        ], md=4),
    ], className="my-2"),


    dbc.Row([
        dbc.Col([
            html.H5("1) Serie temporal", className="text-primary"),
            dcc.Graph(id="graph-line")
        ], width=6),

        dbc.Col([
            html.H5("2) Producción por fuente", className="text-primary"),
            dcc.Checklist(
                id="sources-checklist",
                options=[{"label":s,"value":s} for s in sources_avail],
                value=sources_avail[:3] if len(sources_avail)>=3 else sources_avail,
                inline=True
            ),
            dbc.ButtonGroup([
                dbc.Button("Área", id="btn-area", outline=True, size="sm"),
                dbc.Button("Líneas", id="btn-lines", outline=True, size="sm")
            ]),
            dcc.Graph(id="graph-sources")
        ], width=6),
    ]),


    dbc.Row([
        dbc.Col([
            html.H5("3) Barras mensuales", className="text-primary"),
            dcc.Dropdown(
                id="bar-var-dropdown",
                options=metric_options + [{"label":s,"value":s} for s in sources_avail],
                value=default_metric,
                clearable=False
            ),
            dcc.RadioItems(
                id="bar-agg-radio",
                options=[
                    {"label":"Suma","value":"sum"},
                    {"label":"Promedio","value":"mean"},
                    {"label":"Máximo","value":"max"},
                ],
                inline=True, value="sum"
            ),
            dcc.Graph(id="graph-monthly-bar")
        ], width=6),

        dbc.Col([
            html.H5("4) Heatmap hora vs día", className="text-primary"),
            dcc.Dropdown(
                id="heat-var-dropdown",
                options=metric_options + [{"label":s,"value":s} for s in sources_avail],
                value=default_metric,
                clearable=False
            ),
            dcc.Graph(id="graph-heatmap")
        ], width=6),
    ]),


    dbc.Row([
        dbc.Col([
            html.H5("Vista de datos", className="text-primary"),
            dash_table.DataTable(
                data=df.head(200).to_dict("records"),
                page_size=10,
                style_table={"overflowX":"auto"},
                style_cell={"fontSize":12,"fontFamily":"Arial"}
            )
        ])
    ])
], fluid=True)


# ========== Callbacks ==========

@callback(Output("theme-store","data"),
          Input("btn-light","n_clicks"), Input("btn-dark","n_clicks"))
def switch_theme(n_light, n_dark):
    return {"template":"plotly_dark"} if ctx.triggered_id=="btn-dark" else {"template":"plotly"}


def apply_filter(dfin, s, e):
    return dfin[(dfin["DateTime"] >= pd.to_datetime(s)) &
                (dfin["DateTime"] <= pd.to_datetime(e) + pd.Timedelta(days=1))]


@callback(Output("graph-line","figure"),
          Input("date-range","start_date"), Input("date-range","end_date"),
          Input("metric-dropdown","value"), Input("theme-store","data"))
def graph_line(start, end, metric, theme):
    dff = apply_filter(df, start, end)
    fig = px.line(dff, x="DateTime", y=metric, template=theme["template"])
    fig.update_xaxes(rangeslider_visible=True)
    return fig


@callback(Output("graph-sources","figure"),
          Input("date-range","start_date"), Input("date-range","end_date"),
          Input("sources-checklist","value"),
          Input("btn-area","n_clicks"), Input("btn-lines","n_clicks"),
          Input("theme-store","data"))
def graph_sources(start, end, sources, n_area, n_lines, theme):
    dff = apply_filter(df, start, end)
    monthly = dff.set_index("DateTime")[sources].resample("M").sum().reset_index()
    mode = "lines" if (n_lines or 0) > (n_area or 0) else "area"
    fig = (px.line if mode=="lines" else px.area)(monthly, x="DateTime", y=sources, template=theme["template"])
    return fig


@callback(Output("graph-monthly-bar","figure"),
          Input("date-range","start_date"), Input("date-range","end_date"),
          Input("bar-var-dropdown","value"), Input("bar-agg-radio","value"),
          Input("theme-store","data"))
def graph_bar(start, end, var, agg, theme):
    dff = apply_filter(df, start, end)
    dfa = getattr(dff.groupby("MonthStart")[var], agg)().reset_index()
    fig = px.bar(dfa, x="MonthStart", y=var, template=theme["template"])
    return fig


@callback(Output("graph-heatmap","figure"),
          Input("date-range","start_date"), Input("date-range","end_date"),
          Input("heat-var-dropdown","value"), Input("theme-store","data"))
def heatmap(start, end, var, theme):
    dff = apply_filter(df, start, end)
    pv = dff.pivot_table(index="Weekday", columns="Hour", values=var, aggfunc="mean")
    pv = pv.reindex(["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"])
    fig = go.Figure(go.Heatmap(z=pv.values, x=pv.columns, y=pv.index))
    fig.update_layout(template=theme["template"])
    return fig


# ========== Run ==========

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port, debug=False)

