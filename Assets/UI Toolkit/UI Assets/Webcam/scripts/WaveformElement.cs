using UnityEngine;
using UnityEngine.UIElements;

/// <summary>
/// Waveform display fed by external samples (from Python telemetry).
/// Unity no longer reads the microphone.
/// </summary>
public class WaveformElement : VisualElement
{
    private float[] samples;
    private int sampleCount = 1024;

    private Color barColor = Color.white;

    private float rectWidth;
    private float rectHeight;

    public new class UxmlFactory : UxmlFactory<WaveformElement, UxmlTraits> { }

    public WaveformElement()
    {
        samples = new float[sampleCount];

        style.width = Length.Percent(100);
        style.height = Length.Percent(100);
        style.overflow = Overflow.Visible;

        pickingMode = PickingMode.Ignore;

        this.generateVisualContent += DrawWaveform;

        RegisterCallback<GeometryChangedEvent>(evt =>
        {
            rectWidth = evt.newRect.width;
            rectHeight = evt.newRect.height;
            MarkDirtyRepaint();
        });
    }

    /// <summary>
    /// Update waveform samples (expects small array, will stretch/loop if shorter).
    /// </summary>
    public void SetWaveform(float[] src)
    {
        if (src == null || src.Length == 0)
            return;

        int copyLength = Mathf.Min(src.Length, sampleCount);
        System.Array.Clear(samples, 0, samples.Length);
        System.Array.Copy(src, 0, samples, 0, copyLength);
        MarkDirtyRepaint();
    }

    // =============================
    // Mesh painter
    // =============================
    private void DrawWaveform(MeshGenerationContext ctx)
    {
        if (rectWidth <= 2 || rectHeight <= 2)
            return;

        int barCount = 64;
        float spacing = rectWidth / barCount;
        float barWidth = spacing * 0.6f;

        var mesh = ctx.Allocate(barCount * 4, barCount * 6);

        Vertex[] verts = new Vertex[barCount * 4];
        ushort[] indices = new ushort[barCount * 6];

        for (int i = 0; i < barCount; i++)
        {
            float sample = Mathf.Abs(samples[(i * sampleCount) / barCount]);
            
            // Make it more gentle (reduce multiplier from 6 to 2.5)
            sample = sample * 2.5f;
            
            // Create envelope: shorter at ends, higher at center
            float normalizedPos = (float)i / (barCount - 1); // 0 to 1
            float envelope = Mathf.Sin(normalizedPos * Mathf.PI); // Bell curve: 0 at ends, 1 at center
            
            float barHeight = Mathf.Lerp(5, rectHeight * 0.9f, sample * envelope);

            float x = i * spacing + (spacing - barWidth) * 0.5f;

            // 👇 UI Toolkit 坐标从顶部往下, 所以从中心绘制可见
            float centerY = rectHeight * 0.5f;
            float yTop = centerY - barHeight * 0.5f;
            float yBottom = centerY + barHeight * 0.5f;

            int vi = i * 4;

            verts[vi + 0] = new Vertex() { position = new Vector3(x, yBottom, Vertex.nearZ), tint = barColor };
            verts[vi + 1] = new Vertex() { position = new Vector3(x + barWidth, yBottom, Vertex.nearZ), tint = barColor };
            verts[vi + 2] = new Vertex() { position = new Vector3(x + barWidth, yTop, Vertex.nearZ), tint = barColor };
            verts[vi + 3] = new Vertex() { position = new Vector3(x, yTop, Vertex.nearZ), tint = barColor };

            int ii = i * 6;
            indices[ii + 0] = (ushort)(vi + 0);
            indices[ii + 1] = (ushort)(vi + 1);
            indices[ii + 2] = (ushort)(vi + 2);
            indices[ii + 3] = (ushort)(vi + 0);
            indices[ii + 4] = (ushort)(vi + 2);
            indices[ii + 5] = (ushort)(vi + 3);
        }

        mesh.SetAllVertices(verts);
        mesh.SetAllIndices(indices);
    }
}
