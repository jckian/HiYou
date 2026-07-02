Shader "Custom/GaussianBlur"
{
    Properties
    {
        _MainTex ("Texture", 2D) = "white" {}
        _BlurSize ("Blur Size", Range(0, 10)) = 1.0
    }

    SubShader
    {
        Tags { "RenderType"="Transparent" "Queue"="Transparent" }
        LOD 100

        Pass
        {
            ZWrite Off
            Blend SrcAlpha OneMinusSrcAlpha

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
            float4 _MainTex_TexelSize;
            float _BlurSize;

            v2f vert (appdata v)
            {
                v2f o;
                o.vertex = UnityObjectToClipPos(v.vertex);
                o.uv = v.uv;
                return o;
            }

            fixed4 frag (v2f i) : SV_Target
            {
                float blur = _BlurSize * _MainTex_TexelSize.x;

                fixed4 col = fixed4(0,0,0,1);

                col += tex2D(_MainTex, i.uv + float2(-4.0*blur,0)) * 0.05;
                col += tex2D(_MainTex, i.uv + float2(-3.0*blur,0)) * 0.09;
                col += tex2D(_MainTex, i.uv + float2(-2.0*blur,0)) * 0.12;
                col += tex2D(_MainTex, i.uv + float2(-1.0*blur,0)) * 0.15;

                col += tex2D(_MainTex, i.uv) * 0.16;

                col += tex2D(_MainTex, i.uv + float2(1.0*blur,0)) * 0.15;
                col += tex2D(_MainTex, i.uv + float2(2.0*blur,0)) * 0.12;
                col += tex2D(_MainTex, i.uv + float2(3.0*blur,0)) * 0.09;
                col += tex2D(_MainTex, i.uv + float2(4.0*blur,0)) * 0.05;

                return col;
            }

            ENDCG
        }
    }
}