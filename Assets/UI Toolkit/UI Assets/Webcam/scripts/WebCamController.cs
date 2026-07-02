using UnityEngine;
using UnityEngine.UIElements;

public class WebCamController : MonoBehaviour
{
    private VisualElement root;
    private VisualElement mainPhoto;

    private WebCamTexture webcam;
    private Texture2D camTex;
    private Texture2D processedTex;

    private StyleBackground bg;
    private Texture2D lastTex;   // ← This is very important

    void OnEnable()
    {
        root = GetComponent<UIDocument>().rootVisualElement;
        mainPhoto = root.Q<VisualElement>("mainPhoto");

        bg = new StyleBackground();
        lastTex = null;

        // <<< KEY FIX >>>
        mainPhoto.style.unityBackgroundScaleMode = ScaleMode.ScaleAndCrop;

        InitCamera();
    }

    void InitCamera()
    {
        webcam = new WebCamTexture(WebCamTexture.devices[0].name, 1280, 720, 30);
        webcam.Play();

        camTex = new Texture2D(webcam.width, webcam.height, TextureFormat.RGB24, false);
    }

    void Update()
    {
        Texture2D texToShow = processedTex ?? camTex;

        if (texToShow == camTex && webcam.didUpdateThisFrame)
        {
            // Mirror the webcam horizontally
            Color[] pixels = webcam.GetPixels();
            Color[] mirroredPixels = new Color[pixels.Length];
            
            int width = webcam.width;
            int height = webcam.height;
            
            for (int y = 0; y < height; y++)
            {
                for (int x = 0; x < width; x++)
                {
                    mirroredPixels[y * width + x] = pixels[y * width + (width - 1 - x)];
                }
            }
            
            camTex.SetPixels(mirroredPixels);
            camTex.Apply();
        }

        // 🔥 Critical – Avoid repeated backgroundImage setting
        if (lastTex != texToShow)
        {
            string source = (texToShow == processedTex) ? "Python processed" : "Webcam";
            Debug.Log($"🖥️ Switching display to: {source} ({texToShow.width}x{texToShow.height})");
            
            lastTex = texToShow;
            bg = new StyleBackground(texToShow);
            mainPhoto.style.backgroundImage = bg;
            
            Debug.Log("✅ Background image updated in UI");
        }
    }


    public WebCamTexture GetCameraTexture() => webcam;

    public void SetProcessedFrame(Texture2D t)
    {
        processedTex = t;
    }

    public void ClearProcessedFrame()
    {
        processedTex = null;
    }

    void OnDisable()
    {
    }

    void OnDestroy()
    {
        if (webcam != null && webcam.isPlaying) webcam.Stop();
        if (camTex != null) Destroy(camTex);
        if (processedTex != null) Destroy(processedTex);
    }
}
