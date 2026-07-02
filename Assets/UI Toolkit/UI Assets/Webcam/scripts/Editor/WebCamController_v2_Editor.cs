using UnityEngine;
using UnityEditor;

[CustomEditor(typeof(DrawFacialBoxes))]
public class DrawFacialBoxes_Editor : Editor
{
    private SerializedProperty blurMaterialProp;
    private SerializedProperty webcamControllerProp;

    void OnEnable()
    {
        blurMaterialProp = serializedObject.FindProperty("blurMaterial");
        webcamControllerProp = serializedObject.FindProperty("webcamController");
    }

    public override void OnInspectorGUI()
    {
        serializedObject.Update();

        EditorGUILayout.LabelField("Draw Facial Boxes Settings", EditorStyles.boldLabel);
        EditorGUILayout.Space();
        
        // Dependencies
        EditorGUILayout.PropertyField(webcamControllerProp, new GUIContent("Webcam Controller"));
        EditorGUILayout.Space();

        // Blur Material field
        EditorGUILayout.LabelField("Blur Settings", EditorStyles.boldLabel);
        EditorGUILayout.PropertyField(blurMaterialProp, new GUIContent("Blur Material"));

        // If blur material is assigned, show blur size and darkness sliders
        Material blurMat = blurMaterialProp.objectReferenceValue as Material;
        if (blurMat != null)
        {
            EditorGUILayout.Space();
            
            // Blur Size Slider
            float blurSize = blurMat.HasProperty("_BlurSize") ? blurMat.GetFloat("_BlurSize") : 5f;
            EditorGUI.BeginChangeCheck();
            float newBlurSize = EditorGUILayout.Slider("Blur Intensity", blurSize, 0f, 10f);
            if (EditorGUI.EndChangeCheck())
            {
                Undo.RecordObject(blurMat, "Change Blur Size");
                blurMat.SetFloat("_BlurSize", newBlurSize);
                EditorUtility.SetDirty(blurMat);
            }
            
            // Darkness Slider
            float darkness = blurMat.HasProperty("_Darkness") ? blurMat.GetFloat("_Darkness") : 0.2f;
            EditorGUI.BeginChangeCheck();
            float newDarkness = EditorGUILayout.Slider("Darkness", darkness, 0f, 1f);
            if (EditorGUI.EndChangeCheck())
            {
                Undo.RecordObject(blurMat, "Change Darkness");
                blurMat.SetFloat("_Darkness", newDarkness);
                EditorUtility.SetDirty(blurMat);
            }

            EditorGUILayout.Space();
            EditorGUILayout.HelpBox(
                "Blur: 0 = Sharp, 1-3 = Light, 4-6 = Medium, 7-10 = Heavy\n" +
                "Darkness: 0 = Normal, 1 = Black", 
                MessageType.Info);
        }
        else
        {
            EditorGUILayout.HelpBox("Assign a Blur Material to adjust blur and darkness.", MessageType.Warning);
        }

        serializedObject.ApplyModifiedProperties();
    }
}
