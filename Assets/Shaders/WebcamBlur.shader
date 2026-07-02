Shader "Custom/WebcamBlur"
{
    Properties
    {
        _MainTex ("Texture", 2D) = "white" {}
        _BlurSize ("Blur Size", Range(0, 10)) = 2.0
        _Darkness ("Darkness", Range(0, 1)) = 0.2
    }
    
    SubShader
    {
        Tags { "RenderType"="Opaque" }
        LOD 100

        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"

            struct appdata
            {
                float4 vertex : POSITION;
                float2 uv : TEXCOORD0;
            };

            struct v2f
            {
                float2 uv : TEXCOORD0;
                float4 vertex : SV_POSITION;
            };

            sampler2D _MainTex;
            float4 _MainTex_ST;
            float4 _MainTex_TexelSize;
            float _BlurSize;
            float _Darkness;

            v2f vert (appdata v)
            {
                v2f o;
                o.vertex = UnityObjectToClipPos(v.vertex);
                o.uv = TRANSFORM_TEX(v.uv, _MainTex);
                return o;
            }

            fixed4 frag (v2f i) : SV_Target
            {
                // Gaussian blur with 9 samples
                float2 texelSize = _MainTex_TexelSize.xy * _BlurSize;
                
                fixed4 color = fixed4(0, 0, 0, 0);
                
                // Sample center
                color += tex2D(_MainTex, i.uv) * 0.2270270270;
                
                // Sample surrounding pixels with Gaussian weights
                color += tex2D(_MainTex, i.uv + float2(texelSize.x, 0)) * 0.1945945946;
                color += tex2D(_MainTex, i.uv - float2(texelSize.x, 0)) * 0.1945945946;
                color += tex2D(_MainTex, i.uv + float2(0, texelSize.y)) * 0.1945945946;
                color += tex2D(_MainTex, i.uv - float2(0, texelSize.y)) * 0.1945945946;
                
                color += tex2D(_MainTex, i.uv + float2(texelSize.x, texelSize.y)) * 0.1216216216;
                color += tex2D(_MainTex, i.uv - float2(texelSize.x, texelSize.y)) * 0.1216216216;
                color += tex2D(_MainTex, i.uv + float2(-texelSize.x, texelSize.y)) * 0.1216216216;
                color += tex2D(_MainTex, i.uv - float2(-texelSize.x, texelSize.y)) * 0.1216216216;
                
                // Apply darkness (0 = no darkening, 1 = completely black)
                color.rgb *= (1.0 - _Darkness);
                
                return color;
            }
            ENDCG
        }
    }
}
