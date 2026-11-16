import { useEffect, useRef, useState } from 'react';
import { Spinner } from './ui.jsx';

/** Reads the current design tokens so charts follow light/dark mode. */
function themeLayout() {
  const css = getComputedStyle(document.documentElement);
  const v = (/** @type {string} */ n) => css.getPropertyValue(n).trim();
  return {
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: { color: v('--muted'), family: "Inter, ui-sans-serif, system-ui, sans-serif", size: 12 },
    hoverlabel: { bgcolor: v('--surface'), bordercolor: v('--border'), font: { color: v('--fg'), family: 'Inter, sans-serif' } },
    colorway: ['--c1', '--c2', '--c3', '--c4', '--c5', '--c6'].map(v).concat([v('--muted')]),
    xaxis: { gridcolor: v('--border'), zerolinecolor: v('--border'), linecolor: v('--border') },
    yaxis: { gridcolor: v('--border'), zerolinecolor: v('--border'), linecolor: v('--border') },
    legend: { orientation: 'h', y: -0.2 },
  };
}

/**
 * Renders a Plotly figure JSON built by the API (ChartFactory). Plotly is loaded on demand.
 * @param {{figure: {data: any[], layout?: any}, height?: number}} props
 */
export function Plot({ figure, height = 380 }) {
  const ref = useRef(/** @type {HTMLDivElement | null} */ (null));
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let cancelled = false;
    /** @type {any} */
    let plotly;
    import('plotly.js-dist-min').then((mod) => {
      if (cancelled || !ref.current) return;
      plotly = mod.default ?? mod;
      const base = themeLayout();
      const layout = {
        ...figure.layout,
        ...base,
        xaxis: { ...figure.layout?.xaxis, ...base.xaxis },
        yaxis: { ...figure.layout?.yaxis, ...base.yaxis },
        height,
        autosize: true,
        margin: { l: 50, r: 20, t: figure.layout?.title?.text ? 40 : 16, b: 50 },
      };
      plotly.react(ref.current, figure.data, layout, { responsive: true, displaylogo: false });
      setLoading(false);
    });
    const node = ref.current;
    return () => {
      cancelled = true;
      if (plotly && node) plotly.purge(node);
    };
  }, [figure, height]);
  return (
    <div className="relative w-full" style={{ minHeight: height }}>
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center text-muted">
          <Spinner />
        </div>
      )}
      <div ref={ref} className="w-full" />
    </div>
  );
}
