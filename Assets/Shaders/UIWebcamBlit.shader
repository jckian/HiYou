Shader "Hidden/UIWebcamBlit"
{
    Properties{
        _MainTex ("Texture", 2D) = "white" {}
        _Mirror ("Mirror", Float) = 0
    }

    SubShader{
        Pass{
            ZWrite Off
            Cull Off
            ZTest Always

            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag

            sampler2D _MainTex;
            float _Mirror;

            struct v2f {
                float4 pos : SV_POSITION;
                float2 uv : TEXCOORD0;
            };

            v2f vert(float4 pos : POSITION, float2 uv : TEXCOORD0)
            {
                v2f o;
                o.pos = UnityObjectToClipPos(pos);
                o.uv = uv;
                return o;
            }

            fixed4 frag(v2f i) : SV_Target
            {
                float2 uv = i.uv;
                if (_Mirror > 0.5) uv.x = 1.0 - uv.x;
                return tex2D(_MainTex, uv);
            }
            ENDCG
        }
    }
}