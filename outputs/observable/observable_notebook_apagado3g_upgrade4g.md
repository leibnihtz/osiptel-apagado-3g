# Notebook Observable: Apagado 3G y upgrade 4G

Este archivo contiene las celdas listas para copiar en un notebook de https://observablehq.com/.

Importante: cada bloque ```js representa una celda separada de Observable. Copia solo el contenido dentro del bloque de codigo; no copies las lineas ```js ni ```. Si una celda empieza con `md\`#`, pega tambien el `md\`` inicial; si pegas solo el texto que empieza con `#`, Observable lo interpreta como JavaScript y dara `SyntaxError: Unexpected character '#'`. Si pegas varias definiciones con nombre en una sola celda, por ejemplo `upgradeDistricts = ...` y luego `summary = ...`, Observable dara `SyntaxError: Unexpected token`.

## Datos desde GitHub

Este notebook esta preparado para leer datos directamente desde GitHub raw. Cuando GitHub Actions actualice los archivos mensuales en el repositorio, Observable leera la version nueva al recargar el notebook.

Antes de usarlo, reemplaza `USUARIO/REPO` por tu usuario y nombre real del repositorio:

- `USUARIO`: tu usuario u organizacion de GitHub.
- `REPO`: nombre del repositorio.

---

## Celda 0: Librerias

```js
Plot = require("@observablehq/plot@0.6")
```

```js
Inputs = require("@observablehq/inputs@0.10")
```

```js
d3 = require("d3@7")
```

## Celda 1: Titulo

```js
md`# Apagado 3G y upgrade 4G por distrito

Analisis de distritos donde el 3G de MOVISTAR fue confirmado como apagado, comparando el desempeno 4G antes y despues del breakpoint.

La metrica principal es el cambio promedio de descarga 4G: **post 6 meses - pre 6 meses**.`
```

## Celda 2: Cargar datos

```js
repoBase = "https://raw.githubusercontent.com/USUARIO/REPO/main/outputs/observable/data"
```

```js
allDistricts = d3.json(`${repoBase}/observable_all_districts_with_upgrade_simplified.geojson`)
```

```js
upgradeDistricts = d3.json(`${repoBase}/observable_4g_upgrade_districts.geojson`)
```

```js
summary = d3.csv(`${repoBase}/observable_4g_upgrade_summary_with_ubigeo.csv`, d3.autoType)
```

```js
timeseries = d3.csv(`${repoBase}/observable_shutdown_timeseries.csv`, d3.autoType)
```

## Celda 3: Parametros

```js
viewof metric = Inputs.radio(
  ["delta_4g_download_mbps", "composite_upgrade_score", "delta_4g_latency_ms", "delta_4g_time_pp"],
  {
    label: "Metrica del mapa",
    value: "delta_4g_download_mbps",
    format: d => ({
      delta_4g_download_mbps: "Upgrade descarga 4G",
      composite_upgrade_score: "Score integral",
      delta_4g_latency_ms: "Cambio latencia 4G",
      delta_4g_time_pp: "Cambio tiempo en 4G"
    })[d]
  }
)
```

```js
metricKey = metric ?? "delta_4g_download_mbps"
```

```js
metricInfo = ({
  delta_4g_download_mbps: {
    label: "Upgrade descarga 4G (Mbps)",
    scheme: "RdYlGn",
    reverse: false,
    format: d => `${d?.toFixed(2)} Mbps`
  },
  composite_upgrade_score: {
    label: "Score integral de mejora",
    scheme: "RdYlGn",
    reverse: false,
    format: d => d?.toFixed(3)
  },
  delta_4g_latency_ms: {
    label: "Cambio latencia 4G (ms)",
    scheme: "RdYlGn",
    reverse: true,
    format: d => `${d?.toFixed(1)} ms`
  },
  delta_4g_time_pp: {
    label: "Cambio tiempo en 4G (p.p.)",
    scheme: "RdYlGn",
    reverse: false,
    format: d => `${d?.toFixed(1)} p.p.`
  }
})[metricKey] ?? {
  label: "Upgrade descarga 4G (Mbps)",
  scheme: "RdYlGn",
  reverse: false,
  format: d => `${d?.toFixed(2)} Mbps`
}
```

```js
filteredSummary = summary.filter(d => d.months_post >= 3)
```

## Celda 4: KPIs

```js
html`<div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:18px 0;">
  <div style="border:1px solid #ddd;border-radius:6px;padding:12px;">
    <div style="font-size:12px;color:#666;">Distritos confirmados</div>
    <div style="font-size:28px;font-weight:700;">${summary.length}</div>
  </div>
  <div style="border:1px solid #ddd;border-radius:6px;padding:12px;">
    <div style="font-size:12px;color:#666;">Con >= 3 meses post</div>
    <div style="font-size:28px;font-weight:700;">${filteredSummary.length}</div>
  </div>
  <div style="border:1px solid #ddd;border-radius:6px;padding:12px;">
    <div style="font-size:12px;color:#666;">Mediana upgrade descarga</div>
    <div style="font-size:28px;font-weight:700;">${d3.median(filteredSummary, d => d.delta_4g_download_mbps).toFixed(2)} Mbps</div>
  </div>
  <div style="border:1px solid #ddd;border-radius:6px;padding:12px;">
    <div style="font-size:12px;color:#666;">Departamentos</div>
    <div style="font-size:28px;font-weight:700;">${new Set(summary.map(d => d.department)).size}</div>
  </div>
</div>`
```

## Celda 5: Mapa

```js
md`## Mapa de distritos con apagado 3G confirmado`
```

```js
Plot.plot({
  width,
  height: 720,
  projection: {type: "mercator", domain: allDistricts},
  color: {
    type: "diverging",
    scheme: metricInfo.scheme,
    reverse: metricInfo.reverse,
    label: metricInfo.label,
    legend: true
  },
  marks: [
    Plot.geo(allDistricts, {
      fill: "#f3f4f6",
      stroke: "#d1d5db",
      strokeWidth: 0.25
    }),
    Plot.geo(upgradeDistricts, {
      fill: d => d.properties[metricKey],
      stroke: "#ffffff",
      strokeWidth: 0.6,
      tip: d => ({
        distrito: d.properties.district,
        provincia: d.properties.province,
        departamento: d.properties.department,
        ubigeo: d.properties.ubigeo,
        apagado_3g: d.properties.breakpoint_yearmonth,
        descarga_pre_mbps: d.properties.pre6_4g_download_mbps?.toFixed(2),
        descarga_post_mbps: d.properties.post6_4g_download_mbps?.toFixed(2),
        upgrade_descarga_mbps: d.properties.delta_4g_download_mbps?.toFixed(2),
        cambio_latencia_ms: d.properties.delta_4g_latency_ms?.toFixed(1),
        score: d.properties.composite_upgrade_score?.toFixed(3)
      })
    }),
    Plot.geo(allDistricts, {
      fill: "rgba(255,255,255,0.001)",
      stroke: "transparent",
      tip: d => ({
        distrito: d.properties.district,
        provincia: d.properties.province,
        departamento: d.properties.department,
        ubigeo: d.properties.ubigeo,
        apagado_3g: d.properties.has_shutdown_3g ? d.properties.breakpoint_yearmonth : "sin apagado confirmado",
        upgrade_4g_mbps: d.properties.has_shutdown_3g ? d.properties.delta_4g_download_mbps?.toFixed(2) : null,
        cambio_latencia_ms: d.properties.has_shutdown_3g ? d.properties.delta_4g_latency_ms?.toFixed(1) : null,
        score: d.properties.has_shutdown_3g ? d.properties.composite_upgrade_score?.toFixed(3) : null
      })
    })
  ]
})
```

## Celda 6: Ranking

```js
md`## Distritos con mayor upgrade de descarga 4G`
```

## Celda 5 alternativa: Bubble map estilo D3

Esta version usa D3 directo, parecida al ejemplo Bubble map de D3. Dibuja todos los distritos como silueta, colorea los distritos con apagado confirmado y pone una burbuja sobre cada distrito afectado. La burbuja representa el upgrade absoluto de descarga 4G.

```js
d3BubbleMap = {
  const W = width;
  const H = 760;

  const svg = d3.create("svg")
    .attr("viewBox", [0, 0, W, H])
    .attr("width", W)
    .attr("height", H)
    .attr("style", "max-width:100%;height:auto;background:#ffffff;");

  const projection = d3.geoMercator().fitSize([W, H], allDistricts);
  const path = d3.geoPath(projection);

  const values = allDistricts.features
    .filter(d => d.properties.has_shutdown_3g)
    .map(d => d.properties.delta_4g_download_mbps)
    .filter(Number.isFinite);

  const maxAbs = d3.max(values, d => Math.abs(d)) || 1;
  const color = d3.scaleDiverging(d3.interpolateRdYlGn)
    .domain([-maxAbs, 0, maxAbs]);

  const radius = d3.scaleSqrt()
    .domain([0, d3.max(values, d => Math.abs(d)) || 1])
    .range([1.2, 7]);

  const g = svg.append("g");

  g.append("g")
    .attr("fill", "#f3f4f6")
    .attr("stroke", "#cfd4dc")
    .attr("stroke-width", 0.35)
    .selectAll("path")
    .data(allDistricts.features)
    .join("path")
    .attr("d", path);

  g.append("g")
    .selectAll("path")
    .data(allDistricts.features.filter(d => d.properties.has_shutdown_3g))
    .join("path")
    .attr("d", path)
    .attr("fill", d => color(d.properties.delta_4g_download_mbps))
    .attr("fill-opacity", 0.82)
    .attr("stroke", "#ffffff")
    .attr("stroke-width", 0.7)
    .append("title")
    .text(d => {
      const p = d.properties;
      return `${p.district}, ${p.province}, ${p.department}
UBIGEO: ${p.ubigeo}
Apagado 3G: ${p.breakpoint_yearmonth}
Upgrade descarga 4G: ${p.delta_4g_download_mbps?.toFixed(2)} Mbps
Cambio latencia 4G: ${p.delta_4g_latency_ms?.toFixed(1)} ms
Score integral: ${p.composite_upgrade_score?.toFixed(3)}`;
    });

  g.append("g")
    .attr("fill", "none")
    .attr("stroke", "#111827")
    .attr("stroke-opacity", 0.7)
    .selectAll("circle")
    .data(allDistricts.features.filter(d => d.properties.has_shutdown_3g && Number.isFinite(d.properties.delta_4g_download_mbps)))
    .join("circle")
    .attr("transform", d => `translate(${path.centroid(d)})`)
    .attr("r", d => radius(Math.abs(d.properties.delta_4g_download_mbps)))
    .attr("fill", d => d.properties.delta_4g_download_mbps >= 0 ? "#10b981" : "#ef4444")
    .attr("fill-opacity", 0.38)
    .attr("stroke-width", 1.1)
    .append("title")
    .text(d => {
      const p = d.properties;
      return `${p.district}, ${p.province}, ${p.department}
Upgrade descarga 4G: ${p.delta_4g_download_mbps?.toFixed(2)} Mbps`;
    });

  const legend = svg.append("g")
    .attr("transform", `translate(24, ${H - 96})`);

  legend.append("text")
    .attr("x", 0)
    .attr("y", -14)
    .attr("font-weight", 700)
    .attr("font-size", 13)
    .text("Tamano burbuja: |upgrade descarga 4G|");

  const legendValues = [0.5, 1.5, 3.0].filter(d => d <= maxAbs * 1.15);
  legend.selectAll("circle")
    .data(legendValues)
    .join("circle")
    .attr("cx", (d, i) => i * 76 + 16)
    .attr("cy", 20)
    .attr("r", d => radius(d))
    .attr("fill", "#10b981")
    .attr("fill-opacity", 0.35)
    .attr("stroke", "#111827");

  legend.selectAll("text.value")
    .data(legendValues)
    .join("text")
    .attr("class", "value")
    .attr("x", (d, i) => i * 76 + 16)
    .attr("y", 58)
    .attr("text-anchor", "middle")
    .attr("font-size", 11)
    .text(d => `${d} Mbps`);

  svg.call(
    d3.zoom()
      .scaleExtent([1, 18])
      .on("zoom", event => {
        g.attr("transform", event.transform);
        g.selectAll("circle")
          .attr("r", d => radius(Math.abs(d.properties.delta_4g_download_mbps)) / Math.sqrt(event.transform.k))
          .attr("stroke-width", 1 / event.transform.k);
      })
  );

  return svg.node();
}
```

## Celda 5B: Event-study heatmap D3

Esta visualizacion alinea todos los distritos por el mes del apagado 3G. Cada fila es un distrito y cada columna es un mes relativo al apagado. El color muestra cuantos Mbps esta la descarga 4G por encima o por debajo de su propio promedio pre-apagado de 6 meses. Es util para ver si el cambio fue puntual, gradual o sostenido.

```js
eventTopN = 40
```

```js
eventDistricts = filteredSummary
  .slice()
  .sort((a, b) => d3.descending(a.delta_4g_download_mbps, b.delta_4g_download_mbps))
  .slice(0, eventTopN)
```

```js
eventStudyData = timeseries
  .filter(d => d.relative_month >= -12 && d.relative_month <= 12)
  .map(d => {
    const s = filteredSummary.find(x =>
      x.department === d.ADM_LEVEL_1_NAME &&
      x.province === d.ADM_LEVEL_2_NAME &&
      x.district === d.ADM_LEVEL_3_NAME
    );
    return s ? {
      ...d,
      label: `${d.ADM_LEVEL_3_NAME}, ${d.ADM_LEVEL_2_NAME}`,
      department: d.ADM_LEVEL_1_NAME,
      province: d.ADM_LEVEL_2_NAME,
      district: d.ADM_LEVEL_3_NAME,
      baseline: s.pre6_4g_download_mbps,
      upgrade: s.delta_4g_download_mbps,
      value_vs_baseline: d.AVERAGE_THROUGHPUT_DOWNLOAD_4G - s.pre6_4g_download_mbps
    } : null;
  })
  .filter(Boolean)
  .filter(d => eventDistricts.some(x =>
    x.department === d.department &&
    x.province === d.province &&
    x.district === d.district
  ))
```

```js
d3EventStudyHeatmap = {
  const margin = {top: 46, right: 110, bottom: 56, left: 210};
  const W = width;
  const rowH = 18;
  const labels = eventDistricts.map(d => `${d.district}, ${d.province}`);
  const months = d3.range(-12, 13);
  const H = margin.top + margin.bottom + labels.length * rowH;

  const x = d3.scaleBand()
    .domain(months)
    .range([margin.left, W - margin.right])
    .paddingInner(0.05);

  const y = d3.scaleBand()
    .domain(labels)
    .range([margin.top, H - margin.bottom])
    .paddingInner(0.08);

  const maxAbs = d3.max(eventStudyData, d => Math.abs(d.value_vs_baseline)) || 1;
  const color = d3.scaleDiverging(d3.interpolateRdYlGn)
    .domain([-maxAbs, 0, maxAbs]);

  const svg = d3.create("svg")
    .attr("viewBox", [0, 0, W, H])
    .attr("width", W)
    .attr("height", H)
    .attr("style", "max-width:100%;height:auto;background:#ffffff;");

  svg.append("text")
    .attr("x", margin.left)
    .attr("y", 20)
    .attr("font-size", 16)
    .attr("font-weight", 700)
    .text("Impacto temporal del apagado 3G sobre descarga 4G");

  svg.append("text")
    .attr("x", margin.left)
    .attr("y", 38)
    .attr("font-size", 12)
    .attr("fill", "#6b7280")
    .text("Color = descarga 4G mensual menos promedio pre-apagado de 6 meses");

  svg.append("g")
    .attr("transform", `translate(0,${H - margin.bottom})`)
    .call(d3.axisBottom(x).tickValues(months.filter(d => d % 3 === 0)))
    .call(g => g.select(".domain").remove())
    .call(g => g.append("text")
      .attr("x", W - margin.right)
      .attr("y", 38)
      .attr("fill", "currentColor")
      .attr("text-anchor", "end")
      .text("Mes relativo al apagado 3G"));

  svg.append("g")
    .attr("transform", `translate(${margin.left},0)`)
    .call(d3.axisLeft(y).tickSizeOuter(0))
    .call(g => g.select(".domain").remove())
    .call(g => g.selectAll("text").attr("font-size", 10));

  svg.append("line")
    .attr("x1", x(0) + x.bandwidth() / 2)
    .attr("x2", x(0) + x.bandwidth() / 2)
    .attr("y1", margin.top - 8)
    .attr("y2", H - margin.bottom)
    .attr("stroke", "#b00020")
    .attr("stroke-width", 2);

  svg.append("text")
    .attr("x", x(0) + x.bandwidth() / 2 + 5)
    .attr("y", margin.top - 16)
    .attr("fill", "#b00020")
    .attr("font-size", 11)
    .attr("font-weight", 700)
    .text("apagado");

  svg.append("g")
    .selectAll("rect")
    .data(eventStudyData)
    .join("rect")
    .attr("x", d => x(d.relative_month))
    .attr("y", d => y(d.label))
    .attr("width", x.bandwidth())
    .attr("height", y.bandwidth())
    .attr("fill", d => color(d.value_vs_baseline))
    .append("title")
    .text(d => `${d.district}, ${d.province}, ${d.department}
Mes: ${d.YEARMONTH}
Mes relativo: ${d.relative_month}
Descarga 4G: ${d.AVERAGE_THROUGHPUT_DOWNLOAD_4G?.toFixed(2)} Mbps
Base pre6: ${d.baseline?.toFixed(2)} Mbps
Diferencia vs base: ${d.value_vs_baseline?.toFixed(2)} Mbps
Upgrade pre/post6: ${d.upgrade?.toFixed(2)} Mbps`);

  const legendH = 120;
  const legendY = d3.scaleLinear()
    .domain([-maxAbs, maxAbs])
    .range([margin.top + legendH, margin.top]);

  const defs = svg.append("defs");
  const gradient = defs.append("linearGradient")
    .attr("id", "event-heatmap-gradient")
    .attr("x1", "0%")
    .attr("x2", "0%")
    .attr("y1", "100%")
    .attr("y2", "0%");

  d3.range(0, 1.01, 0.1).forEach(t => {
    const v = -maxAbs + t * 2 * maxAbs;
    gradient.append("stop")
      .attr("offset", `${t * 100}%`)
      .attr("stop-color", color(v));
  });

  svg.append("rect")
    .attr("x", W - margin.right + 34)
    .attr("y", margin.top)
    .attr("width", 14)
    .attr("height", legendH)
    .attr("fill", "url(#event-heatmap-gradient)");

  svg.append("g")
    .attr("transform", `translate(${W - margin.right + 48},0)`)
    .call(d3.axisRight(legendY).ticks(5))
    .call(g => g.select(".domain").remove());

  svg.append("text")
    .attr("x", W - margin.right + 22)
    .attr("y", margin.top - 10)
    .attr("font-size", 11)
    .attr("font-weight", 700)
    .text("Mbps vs base");

  return svg.node();
}
```

```js
topDownload = filteredSummary
  .slice()
  .sort((a, b) => d3.descending(a.delta_4g_download_mbps, b.delta_4g_download_mbps))
  .slice(0, 15)
```

```js
d3Ranking = {
  const margin = {top: 28, right: 28, bottom: 46, left: 190};
  const W = width;
  const H = 520;
  const data = topDownload.slice().sort((a, b) => d3.ascending(a.delta_4g_download_mbps, b.delta_4g_download_mbps));

  const x = d3.scaleLinear()
    .domain([Math.min(0, d3.min(data, d => d.delta_4g_download_mbps)), d3.max(data, d => d.delta_4g_download_mbps)])
    .nice()
    .range([margin.left, W - margin.right]);

  const y = d3.scaleBand()
    .domain(data.map(d => `${d.district}, ${d.province}`))
    .range([H - margin.bottom, margin.top])
    .padding(0.22);

  const color = d3.scaleOrdinal()
    .domain([...new Set(filteredSummary.map(d => d.department))].sort())
    .range(d3.schemeTableau10);

  const svg = d3.create("svg")
    .attr("viewBox", [0, 0, W, H])
    .attr("width", W)
    .attr("height", H)
    .attr("style", "max-width:100%;height:auto;background:#ffffff;");

  svg.append("g")
    .attr("transform", `translate(0,${H - margin.bottom})`)
    .call(d3.axisBottom(x).ticks(7))
    .call(g => g.select(".domain").remove())
    .call(g => g.append("text")
      .attr("x", W - margin.right)
      .attr("y", 38)
      .attr("fill", "currentColor")
      .attr("text-anchor", "end")
      .text("Upgrade descarga 4G (Mbps)"));

  svg.append("g")
    .attr("transform", `translate(${margin.left},0)`)
    .call(d3.axisLeft(y).tickSizeOuter(0))
    .call(g => g.select(".domain").remove());

  svg.append("g")
    .attr("stroke", "#e5e7eb")
    .attr("stroke-opacity", 0.9)
    .selectAll("line")
    .data(x.ticks(7))
    .join("line")
    .attr("x1", d => x(d))
    .attr("x2", d => x(d))
    .attr("y1", margin.top)
    .attr("y2", H - margin.bottom);

  svg.append("line")
    .attr("x1", x(0))
    .attr("x2", x(0))
    .attr("y1", margin.top)
    .attr("y2", H - margin.bottom)
    .attr("stroke", "#111827")
    .attr("stroke-width", 1);

  svg.append("g")
    .selectAll("rect")
    .data(data)
    .join("rect")
    .attr("x", d => x(Math.min(0, d.delta_4g_download_mbps)))
    .attr("y", d => y(`${d.district}, ${d.province}`))
    .attr("width", d => Math.abs(x(d.delta_4g_download_mbps) - x(0)))
    .attr("height", y.bandwidth())
    .attr("rx", 3)
    .attr("fill", d => color(d.department))
    .append("title")
    .text(d => `${d.district}, ${d.province}, ${d.department}
Upgrade descarga 4G: ${d.delta_4g_download_mbps.toFixed(2)} Mbps
Pre: ${d.pre6_4g_download_mbps.toFixed(2)} Mbps
Post: ${d.post6_4g_download_mbps.toFixed(2)} Mbps
Apagado 3G: ${d.breakpoint_yearmonth}`);

  svg.append("g")
    .attr("font-size", 11)
    .attr("fill", "#111827")
    .selectAll("text")
    .data(data)
    .join("text")
    .attr("x", d => x(d.delta_4g_download_mbps) + (d.delta_4g_download_mbps >= 0 ? 5 : -5))
    .attr("y", d => y(`${d.district}, ${d.province}`) + y.bandwidth() / 2)
    .attr("dy", "0.35em")
    .attr("text-anchor", d => d.delta_4g_download_mbps >= 0 ? "start" : "end")
    .text(d => d.delta_4g_download_mbps.toFixed(2));

  return svg.node();
}
```

## Celda 7: Antes vs despues

```js
md`## Comparacion antes vs despues del apagado`
```

```js
maxDownload = d3.max(filteredSummary, d => Math.max(d.pre6_4g_download_mbps, d.post6_4g_download_mbps))
```

```js
d3BeforeAfter = {
  const margin = {top: 28, right: 28, bottom: 62, left: 72};
  const W = width;
  const H = 620;
  const limit = Math.ceil(maxDownload + 1);
  const data = filteredSummary;

  const x = d3.scaleLinear().domain([0, limit]).nice().range([margin.left, W - margin.right]);
  const y = d3.scaleLinear().domain([0, limit]).nice().range([H - margin.bottom, margin.top]);
  const color = d3.scaleOrdinal()
    .domain([...new Set(data.map(d => d.department))].sort())
    .range(d3.schemeTableau10);
  const r = d3.scaleSqrt()
    .domain([0, d3.max(data, d => d.post6_4g_download_measurements || 1)])
    .range([3, 10]);

  const svg = d3.create("svg")
    .attr("viewBox", [0, 0, W, H])
    .attr("width", W)
    .attr("height", H)
    .attr("style", "max-width:100%;height:auto;background:#ffffff;");

  svg.append("g")
    .attr("transform", `translate(0,${H - margin.bottom})`)
    .call(d3.axisBottom(x))
    .call(g => g.select(".domain").remove())
    .call(g => g.append("text")
      .attr("x", W - margin.right)
      .attr("y", 44)
      .attr("fill", "currentColor")
      .attr("text-anchor", "end")
      .text("Antes del apagado: descarga 4G promedio (Mbps)"));

  svg.append("g")
    .attr("transform", `translate(${margin.left},0)`)
    .call(d3.axisLeft(y))
    .call(g => g.select(".domain").remove())
    .call(g => g.append("text")
      .attr("x", -margin.left + 4)
      .attr("y", margin.top - 12)
      .attr("fill", "currentColor")
      .attr("text-anchor", "start")
      .text("Despues del apagado: descarga 4G promedio (Mbps)"));

  svg.append("g")
    .attr("stroke", "#e5e7eb")
    .selectAll("line")
    .data(x.ticks())
    .join("line")
    .attr("x1", d => x(d))
    .attr("x2", d => x(d))
    .attr("y1", margin.top)
    .attr("y2", H - margin.bottom);

  svg.append("g")
    .attr("stroke", "#e5e7eb")
    .selectAll("line")
    .data(y.ticks())
    .join("line")
    .attr("x1", margin.left)
    .attr("x2", W - margin.right)
    .attr("y1", d => y(d))
    .attr("y2", d => y(d));

  svg.append("line")
    .attr("x1", x(0))
    .attr("y1", y(0))
    .attr("x2", x(limit))
    .attr("y2", y(limit))
    .attr("stroke", "#6b7280")
    .attr("stroke-dasharray", "5,5");

  svg.append("g")
    .attr("fill-opacity", 0.78)
    .attr("stroke", "#ffffff")
    .attr("stroke-width", 0.8)
    .selectAll("circle")
    .data(data)
    .join("circle")
    .attr("cx", d => x(d.pre6_4g_download_mbps))
    .attr("cy", d => y(d.post6_4g_download_mbps))
    .attr("r", d => r(d.post6_4g_download_measurements || 1))
    .attr("fill", d => color(d.department))
    .append("title")
    .text(d => `${d.district}, ${d.province}, ${d.department}
Pre 4G: ${d.pre6_4g_download_mbps.toFixed(2)} Mbps
Post 4G: ${d.post6_4g_download_mbps.toFixed(2)} Mbps
Upgrade: ${d.delta_4g_download_mbps.toFixed(2)} Mbps`);

  return svg.node();
}
```

## Celda 8: Relacion descarga-latencia

```js
md`## Upgrade de descarga versus cambio de latencia`
```

```js
d3DownloadLatency = {
  const margin = {top: 28, right: 28, bottom: 58, left: 76};
  const W = width;
  const H = 560;
  const data = filteredSummary;

  const x = d3.scaleLinear()
    .domain(d3.extent(data, d => d.delta_4g_download_mbps))
    .nice()
    .range([margin.left, W - margin.right]);
  const y = d3.scaleLinear()
    .domain(d3.extent(data, d => d.delta_4g_latency_ms))
    .nice()
    .range([H - margin.bottom, margin.top]);
  const color = d3.scaleOrdinal()
    .domain([...new Set(data.map(d => d.department))].sort())
    .range(d3.schemeTableau10);

  const svg = d3.create("svg")
    .attr("viewBox", [0, 0, W, H])
    .attr("width", W)
    .attr("height", H)
    .attr("style", "max-width:100%;height:auto;background:#ffffff;");

  svg.append("g")
    .attr("transform", `translate(0,${H - margin.bottom})`)
    .call(d3.axisBottom(x))
    .call(g => g.select(".domain").remove())
    .call(g => g.append("text")
      .attr("x", W - margin.right)
      .attr("y", 42)
      .attr("fill", "currentColor")
      .attr("text-anchor", "end")
      .text("Upgrade descarga 4G (Mbps)"));

  svg.append("g")
    .attr("transform", `translate(${margin.left},0)`)
    .call(d3.axisLeft(y))
    .call(g => g.select(".domain").remove())
    .call(g => g.append("text")
      .attr("x", -margin.left + 4)
      .attr("y", margin.top - 12)
      .attr("fill", "currentColor")
      .attr("text-anchor", "start")
      .text("Cambio latencia 4G (ms). Negativo = mejora"));

  svg.append("line")
    .attr("x1", x(0)).attr("x2", x(0))
    .attr("y1", margin.top).attr("y2", H - margin.bottom)
    .attr("stroke", "#9ca3af")
    .attr("stroke-dasharray", "4,4");

  svg.append("line")
    .attr("x1", margin.left).attr("x2", W - margin.right)
    .attr("y1", y(0)).attr("y2", y(0))
    .attr("stroke", "#9ca3af")
    .attr("stroke-dasharray", "4,4");

  svg.append("g")
    .attr("fill-opacity", 0.78)
    .attr("stroke", "#ffffff")
    .attr("stroke-width", 0.8)
    .selectAll("circle")
    .data(data)
    .join("circle")
    .attr("cx", d => x(d.delta_4g_download_mbps))
    .attr("cy", d => y(d.delta_4g_latency_ms))
    .attr("r", 5)
    .attr("fill", d => color(d.department))
    .append("title")
    .text(d => `${d.district}, ${d.province}, ${d.department}
Upgrade descarga 4G: ${d.delta_4g_download_mbps.toFixed(2)} Mbps
Cambio latencia 4G: ${d.delta_4g_latency_ms.toFixed(1)} ms`);

  return svg.node();
}
```

## Celda 9: Selector geografico en cascada

```js
selectorSummary = summary
```

```js
departmentOptions = [...new Set(selectorSummary.map(d => d.department))].sort(d3.ascending)
```

```js
viewof selectedDepartment = Inputs.select(departmentOptions, {
  label: "Departamento",
  value: departmentOptions.includes("Cusco") ? "Cusco" : departmentOptions[0]
})
```

```js
provinceOptions = [...new Set(
  selectorSummary
    .filter(d => d.department === selectedDepartment)
    .map(d => d.province)
)].sort(d3.ascending)
```

```js
viewof selectedProvince = Inputs.select(provinceOptions, {
  label: "Provincia",
  value: provinceOptions.includes("Cusco") ? "Cusco" : provinceOptions[0]
})
```

```js
districtOptions = selectorSummary
  .filter(d => d.department === selectedDepartment && d.province === selectedProvince)
  .slice()
  .sort((a, b) => d3.ascending(a.district, b.district))
  .map(d => d.district)
```

```js
viewof selectedDistrict = Inputs.select(districtOptions, {
  label: "Distrito",
  value: districtOptions.includes("San Jeronimo") ? "San Jeronimo" : districtOptions[0]
})
```

```js
selectedDistrictLabel = `${selectedDistrict}, ${selectedProvince}, ${selectedDepartment}`
```

```js
selectedSummary = selectorSummary.find(d =>
  d.department === selectedDepartment &&
  d.province === selectedProvince &&
  d.district === selectedDistrict
)
```

```js
html`<div style="border:1px solid #ddd;border-radius:6px;padding:12px;margin:8px 0 16px 0;background:#fafafa;">
  <div style="font-size:13px;color:#666;">Seleccion actual</div>
  <div style="font-size:20px;font-weight:700;">${selectedDistrictLabel}</div>
  <div style="font-size:13px;margin-top:6px;">
    Apagado 3G: <b>${selectedSummary?.breakpoint_yearmonth ?? "n/d"}</b> -
    Upgrade descarga 4G: <b>${selectedSummary?.delta_4g_download_mbps?.toFixed(2) ?? "n/d"} Mbps</b> -
    Cambio latencia: <b>${selectedSummary?.delta_4g_latency_ms?.toFixed(1) ?? "n/d"} ms</b>
  </div>
</div>`
```

```js
selectedSeries = timeseries
  .filter(d =>
    d.ADM_LEVEL_1_NAME === selectedDepartment &&
    d.ADM_LEVEL_2_NAME === selectedProvince &&
    d.ADM_LEVEL_3_NAME === selectedDistrict
  )
  .sort((a, b) => d3.ascending(a.relative_month, b.relative_month))
```

```js
selectedSeries.length
```

Si esta ultima celda devuelve `0`, revisa que la seleccion exista en `timeseries`. Con los archivos generados deberia devolver una serie mensual.

## Celda 10: Serie temporal por distrito

```js
md`## Evolucion mensual del distrito seleccionado`
```

```js
selectedTimeChart = {
  const months = selectedSeries
    .map(d => d.relative_month)
    .filter(Number.isFinite);
  const [minMonth, maxMonth] = d3.extent(months);

  return {
    margin: {top: 28, right: 90, bottom: 54, left: 70},
    W: width,
    xDomain: [Math.min(minMonth ?? -1, 0), Math.max(maxMonth ?? 1, 0)]
  };
}
```

```js
d3SelectedDownload = {
  const {margin, W, xDomain} = selectedTimeChart;
  const H = 460;
  const data = selectedSeries;

  const x = d3.scaleLinear()
    .domain(xDomain)
    .nice()
    .range([margin.left, W - margin.right]);
  const y = d3.scaleLinear()
    .domain([0, d3.max(data, d => Math.max(
      d.AVERAGE_THROUGHPUT_DOWNLOAD_4G ?? 0,
      d.AVERAGE_THROUGHPUT_DOWNLOAD_3G ?? 0
    ))])
    .nice()
    .range([H - margin.bottom, margin.top]);

  const svg = d3.create("svg")
    .attr("viewBox", [0, 0, W, H])
    .attr("width", W)
    .attr("height", H)
    .attr("style", "max-width:100%;height:auto;background:#ffffff;");

  svg.append("g")
    .attr("transform", `translate(0,${H - margin.bottom})`)
    .call(d3.axisBottom(x))
    .call(g => g.select(".domain").remove())
    .call(g => g.append("text")
      .attr("x", W - margin.right)
      .attr("y", 40)
      .attr("fill", "currentColor")
      .attr("text-anchor", "end")
      .text("Mes relativo al apagado 3G"));

  svg.append("g")
    .attr("transform", `translate(${margin.left},0)`)
    .call(d3.axisLeft(y))
    .call(g => g.select(".domain").remove())
    .call(g => g.append("text")
      .attr("x", -margin.left + 4)
      .attr("y", margin.top - 12)
      .attr("fill", "currentColor")
      .attr("text-anchor", "start")
      .text("Descarga promedio (Mbps)"));

  svg.append("line")
    .attr("x1", x(0))
    .attr("x2", x(0))
    .attr("y1", margin.top)
    .attr("y2", H - margin.bottom)
    .attr("stroke", "#b00020")
    .attr("stroke-width", 2);

  const series = [
    {name: "4G", key: "AVERAGE_THROUGHPUT_DOWNLOAD_4G", color: "#2563eb", width: 2.4},
    {name: "3G", key: "AVERAGE_THROUGHPUT_DOWNLOAD_3G", color: "#ef4444", width: 2.0}
  ];

  for (const s of series) {
    svg.append("path")
      .datum(data)
      .attr("fill", "none")
      .attr("stroke", s.color)
      .attr("stroke-width", s.width)
      .attr("stroke-dasharray", s.name === "3G" ? "5,3" : null)
      .attr("d", d3.line()
        .defined(d => Number.isFinite(d[s.key]))
        .x(d => x(d.relative_month))
        .y(d => y(d[s.key])));

    svg.append("g")
      .attr("fill", s.color)
      .attr("stroke", "#ffffff")
      .attr("stroke-width", 1)
      .selectAll("circle")
      .data(data.filter(d => Number.isFinite(d[s.key])))
      .join("circle")
      .attr("cx", d => x(d.relative_month))
      .attr("cy", d => y(d[s.key]))
      .attr("r", s.name === "4G" ? 4 : 3.5)
      .append("title")
      .text(d => `Red: ${s.name}
Mes: ${d.YEARMONTH}
Mes relativo: ${d.relative_month}
Descarga ${s.name}: ${d[s.key]?.toFixed(2)} Mbps`);
  }

  svg.append("g")
    .attr("transform", `translate(${W - margin.right - 78},${margin.top + 4})`)
    .selectAll("g")
    .data(series)
    .join("g")
    .attr("transform", (d, i) => `translate(0,${i * 20})`)
    .call(g => {
      g.append("line")
        .attr("x1", 0)
        .attr("x2", 24)
        .attr("y1", 0)
        .attr("y2", 0)
        .attr("stroke", d => d.color)
        .attr("stroke-width", d => d.width)
        .attr("stroke-dasharray", d => d.name === "3G" ? "5,3" : null);
      g.append("text")
        .attr("x", 30)
        .attr("y", 0)
        .attr("dy", "0.35em")
        .attr("font-size", 12)
        .attr("font-weight", 700)
        .attr("fill", d => d.color)
        .text(d => d.name);
    });

  return svg.node();
}
```

```js
d3SelectedNetworkTime = {
  const {margin, W, xDomain} = selectedTimeChart;
  const H = 420;
  const data = selectedSeries;

  const x = d3.scaleLinear()
    .domain(xDomain)
    .nice()
    .range([margin.left, W - margin.right]);
  const y = d3.scaleLinear()
    .domain([0, 100])
    .range([H - margin.bottom, margin.top]);

  const series = [
    {name: "3G", key: "TIME_PERCENTAGE_3G", color: "#ef4444"},
    {name: "4G", key: "TIME_PERCENTAGE_4G", color: "#2563eb"}
  ];

  const svg = d3.create("svg")
    .attr("viewBox", [0, 0, W, H])
    .attr("width", W)
    .attr("height", H)
    .attr("style", "max-width:100%;height:auto;background:#ffffff;");

  svg.append("g")
    .attr("transform", `translate(0,${H - margin.bottom})`)
    .call(d3.axisBottom(x))
    .call(g => g.select(".domain").remove())
    .call(g => g.append("text")
      .attr("x", W - margin.right)
      .attr("y", 40)
      .attr("fill", "currentColor")
      .attr("text-anchor", "end")
      .text("Mes relativo al apagado 3G"));

  svg.append("g")
    .attr("transform", `translate(${margin.left},0)`)
    .call(d3.axisLeft(y).ticks(6).tickFormat(d => `${d}%`))
    .call(g => g.select(".domain").remove())
    .call(g => g.append("text")
      .attr("x", -margin.left + 4)
      .attr("y", margin.top - 12)
      .attr("fill", "currentColor")
      .attr("text-anchor", "start")
      .text("Porcentaje de tiempo en red"));

  svg.append("line")
    .attr("x1", x(0))
    .attr("x2", x(0))
    .attr("y1", margin.top)
    .attr("y2", H - margin.bottom)
    .attr("stroke", "#b00020")
    .attr("stroke-width", 2);

  for (const s of series) {
    svg.append("path")
      .datum(data)
      .attr("fill", "none")
      .attr("stroke", s.color)
      .attr("stroke-width", 2.2)
      .attr("d", d3.line()
        .x(d => x(d.relative_month))
        .y(d => y(d[s.key])));

    svg.append("text")
      .attr("x", W - margin.right + 12)
      .attr("y", y(data.at(-1)?.[s.key] ?? 0))
      .attr("dy", "0.35em")
      .attr("fill", s.color)
      .attr("font-weight", 700)
      .text(s.name);
  }

  svg.append("g")
    .selectAll("circle")
    .data(data.flatMap(d => series.map(s => ({...d, network: s.name, key: s.key, color: s.color, value: d[s.key]}))))
    .join("circle")
    .attr("cx", d => x(d.relative_month))
    .attr("cy", d => y(d.value))
    .attr("r", 3)
    .attr("fill", d => d.color)
    .append("title")
    .text(d => `Red: ${d.network}
Mes: ${d.YEARMONTH}
Mes relativo: ${d.relative_month}
Tiempo: ${d.value?.toFixed(1)}%`);

  return svg.node();
}
```

## Celda 11: Tabla final

```js
Inputs.table(filteredSummary, {
  columns: [
    "department",
    "province",
    "district",
    "ubigeo",
    "breakpoint_yearmonth",
    "pre6_4g_download_mbps",
    "post6_4g_download_mbps",
    "delta_4g_download_mbps",
    "delta_4g_latency_ms",
    "delta_4g_time_pp",
    "composite_upgrade_score"
  ],
  header: {
    department: "Departamento",
    province: "Provincia",
    district: "Distrito",
    ubigeo: "UBIGEO",
    breakpoint_yearmonth: "Apagado 3G",
    pre6_4g_download_mbps: "Pre DL 4G",
    post6_4g_download_mbps: "Post DL 4G",
    delta_4g_download_mbps: "Upgrade DL 4G",
    delta_4g_latency_ms: "Delta latencia",
    delta_4g_time_pp: "Delta tiempo 4G",
    composite_upgrade_score: "Score"
  },
  sort: "delta_4g_download_mbps",
  reverse: true
})
```

## Nota de interpretacion

```js
md`### Lectura sugerida

Los distritos ubicados arriba de la diagonal en el scatter mejoraron su descarga 4G despues del apagado 3G. En el mapa, los colores mas favorables muestran mayor mejora segun la metrica elegida. Para evitar conclusiones fragiles, el ranking principal filtra distritos con al menos 3 meses de datos posteriores al apagado.`
```

