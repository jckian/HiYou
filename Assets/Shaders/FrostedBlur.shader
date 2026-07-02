Shader "Custom/FrostedBlur"
{
    Properties
    {
        _MainTex ("Texture", 2D) = "white" {}
        _BlurSize ("Blur Size", Range(0, 10)) = 2.0
        _Brightness ("Brightness", Range(0, 2)) = 1.05
        _TintColor ("Tint Color", Color) = (1,1,1,0.5)   // 毛玻璃的透光颜色
        _NoiseStrength ("Noise Strength", Range(0, 1)) = 0.1  // 玻璃颗粒感
    }
    
    SubShader
    {
        Tags{ "RenderType" = "Opaque" }

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
            float4 _TintColor;
            float _NoiseStrength;

            struct appdata {
                float4 vertex : POSITION;
                float2 uv : TEXCOORD0;
            };

            struct v2f {
                float2 uv : TEXCOORD0;
                float4 vertex : SV_POSITION;
            };

            v2f vert (appdata v)
            {
                v2f o;
                o.vertex = UnityObjectToClipPos(v.vertex);
                o.uv = v.uv;
                return o;
            }

            // Simple noise function for frosted particles
            float hash21(float2 p)
            {
                p = frac(p * float2(123.34, 345.45));
                p += dot(p, p + 34.345);
                return frac(p.x * p.y);
            }

            fixed4 frag (v2f i) : SV_Target
            {
                float2 pixel = _MainTex_TexelSize.xy * _BlurSize;

                // 9-tap Gaussian blur
                float2 offsets[9] = {
                    float2(-4, 0), float2(-3, 0), float2(-2, 0),
                    float2(-1, 0), float2(0,0),
                    float2(1, 0), float2(2, 0), float2(3, 0), float2(4, 0),
                };

                float weights[9] = {0.05, 0.09, 0.12, 0.15, 0.16, 0.15, 0.12, 0.09, 0.05};

                float4 blur = 0;

                for (int k = 0; k < 9; k++)
                    blur += tex2D(_MainTex, i.uv + offsets[k] * pixel) * weights[k];

                // Add frosted noise
                float noise = hash21(i.uv * 800) * _NoiseStrength;

                // Add brightness + tint color
                blur.rgb = blur.rgb * _Brightness + _TintColor.rgb * _TintColor.a;

                blur.rgb += noise;

                return blur;
            }

            ENDCG
        }
    }
}