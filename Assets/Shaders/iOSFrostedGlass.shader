Shader "Custom/iOSFrostedGlass"
{
    Properties
    {
        _MainTex ("Background", 2D) = "white" {}
        _BlurSize ("Blur Size", Range(0, 10)) = 4
        _Brightness ("Brightness", Range(0, 2)) = 1.1
        _Desaturate ("Desaturate", Range(0, 1)) = 0.35
        _HazeColor ("Haze (Tint)", Color) = (1,1,1,0.25)
        _BloomStrength ("Bloom Strength", Range(0, 1)) = 0.15
    }

    SubShader
    {
        Tags { "RenderType"="Opaque" }
        LOD 200

        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"

            sampler2D _MainTex;
            float4 _MainTex_TexelSize;

            float _BlurSize;
            float _Brightness;
            float _Desaturate;
            float4 _HazeColor;
            float _BloomStrength;

            struct appdata {
                float4 vertex : POSITION;
                float2 uv : TEXCOORD0;
            };

            struct v2f {
                float2 uv : TEXCOORD0;
                float4 pos : SV_POSITION;
            };

            v2f vert (appdata v)
            {
                v2f o;
                o.pos = UnityObjectToClipPos(v.vertex);
                o.uv = v.uv;
                return o;
            }

            // Gaussian weights (iOS quality)
            const float weights[9] = {
                0.05, 0.09, 0.12, 0.15,
                0.16,
                0.15, 0.12, 0.09, 0.05
            };

            fixed4 GaussianBlur(float2 uv)
            {
                float2 offset = _MainTex_TexelSize.xy * _BlurSize;
                fixed4 sum = 0;

                for (int i = -4; i <= 4; i++)
                {
                    sum += tex2D(_MainTex, uv + float2(offset.x * i, 0)) * weights[i+4];
                }

                fixed4 finalBlur = 0;

                for (int j = -4; j <= 4; j++)
                {
                    finalBlur += tex2D(_MainTex, uv + float2(0, offset.y * j)) * weights[j+4];
                }

                return (sum + finalBlur) * 0.5;
            }

            // Desaturate function
            float3 DesaturateColor(float3 col, float amount)
            {
                float luminance = dot(col, float3(0.299, 0.587, 0.114));
                return lerp(col, luminance.xxx, amount);
            }

            fixed4 frag(v2f i) : SV_Target
            {
                // 1. Blur
                fixed4 blurred = GaussianBlur(i.uv);

                // 2. Slight desaturation
                blurred.rgb = DesaturateColor(blurred.rgb, _Desaturate);

                // 3. Increase brightness slightly
                blurred.rgb *= _Brightness;

                // 4. Add iOS haze glow (white tint)
                blurred.rgb = lerp(blurred.rgb, blurred.rgb + _HazeColor.rgb, _HazeColor.a);

                // 5. Add soft bloom
                float bloom = smoothstep(0.5, 1.0, max(blurred.r, max(blurred.g, blurred.b)));
                blurred.rgb += bloom * _BloomStrength;

                return blurred;
            }
            ENDCG
        }
    }
}