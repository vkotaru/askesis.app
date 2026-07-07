package app.askesis.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.unit.dp

/**
 * Minimal hand-rolled charts (no external charting dependency) for the Today dashboard, mirroring
 * the web app's small inline SVG charts. Colors come from the active theme so they follow the
 * user's chosen color scheme.
 */

/**
 * A line chart with light gridlines, the main series (dots + line) and an optional dashed
 * moving-average overlay — the web's Weight Trend look. Both series share one min/max scale.
 * Draws nothing meaningful for < 2 points.
 */
@Composable
fun LineChart(
    points: List<Float>,
    modifier: Modifier = Modifier.fillMaxWidth().height(140.dp),
    lineColor: Color = MaterialTheme.colorScheme.primary,
    avg: List<Float> = emptyList(),
    avgColor: Color = MaterialTheme.colorScheme.tertiary,
    gridColor: Color = MaterialTheme.colorScheme.outlineVariant,
) {
    Canvas(modifier) {
        if (points.size < 2) return@Canvas
        val all = points + avg
        val min = all.min()
        val max = all.max()
        val range = (max - min).takeIf { it > 0f } ?: 1f
        val stepX = size.width / (points.size - 1)
        val pad = size.height * 0.12f
        val usable = size.height - pad * 2
        fun y(v: Float) = pad + usable * (1f - (v - min) / range)

        // horizontal gridlines
        for (i in 0..3) {
            val gy = pad + usable * i / 3f
            drawLine(gridColor, Offset(0f, gy), Offset(size.width, gy), strokeWidth = 1.5f)
        }

        // optional moving-average (dashed)
        if (avg.size == points.size) {
            val ap = Path()
            avg.forEachIndexed { i, v ->
                val px = stepX * i; val py = y(v)
                if (i == 0) ap.moveTo(px, py) else ap.lineTo(px, py)
            }
            drawPath(
                ap, color = avgColor,
                style = Stroke(
                    width = 3f, cap = StrokeCap.Round,
                    pathEffect = PathEffect.dashPathEffect(floatArrayOf(12f, 10f)),
                ),
            )
        }

        // main series
        val path = Path()
        points.forEachIndexed { i, v ->
            val px = stepX * i; val py = y(v)
            if (i == 0) path.moveTo(px, py) else path.lineTo(px, py)
        }
        drawPath(path, color = lineColor, style = Stroke(width = 5f, cap = StrokeCap.Round))
        points.forEachIndexed { i, v ->
            drawCircle(lineColor, radius = 6f, center = Offset(stepX * i, y(v)))
        }
    }
}

/** A vertical bar chart, one bar per value. Bars share a baseline at 0. */
@Composable
fun BarChart(
    values: List<Float>,
    modifier: Modifier = Modifier.fillMaxWidth().height(120.dp),
    barColor: Color = MaterialTheme.colorScheme.primary,
) {
    Canvas(modifier) {
        if (values.isEmpty()) return@Canvas
        val max = values.max().takeIf { it > 0f } ?: 1f
        val slot = size.width / values.size
        val barWidth = slot * 0.6f
        values.forEachIndexed { i, v ->
            val h = size.height * (v / max)
            val left = slot * i + (slot - barWidth) / 2f
            drawRect(
                color = barColor,
                topLeft = Offset(left, size.height - h),
                size = androidx.compose.ui.geometry.Size(barWidth, h),
            )
        }
    }
}

/** A horizontal progress bar comparing [value] to a [target]; tints [overColor] when over target. */
@Composable
fun TargetProgressBar(
    value: Float,
    target: Float,
    modifier: Modifier = Modifier.fillMaxWidth().height(16.dp),
    fillColor: Color = MaterialTheme.colorScheme.primary,
    trackColor: Color = MaterialTheme.colorScheme.surfaceVariant,
    overColor: Color = MaterialTheme.colorScheme.error,
) {
    Canvas(modifier) {
        val radius = size.height / 2f
        val corner = androidx.compose.ui.geometry.CornerRadius(radius, radius)
        drawRoundRect(color = trackColor, cornerRadius = corner)
        if (target <= 0f) return@Canvas
        val frac = (value / target).coerceIn(0f, 1f)
        if (frac <= 0f) return@Canvas
        drawRoundRect(
            color = if (value > target) overColor else fillColor,
            size = androidx.compose.ui.geometry.Size(size.width * frac, size.height),
            cornerRadius = corner,
        )
    }
}
