using UnityEngine;
using UnityEditor;
using System.IO;

[CustomEditor(typeof(PythonLauncher))]
public class PythonLauncherEditor : Editor
{
    SerializedProperty pythonExePathProp;
    SerializedProperty pythonScriptPathProp;

    void OnEnable()
    {
        pythonExePathProp = serializedObject.FindProperty("pythonExePath");
        pythonScriptPathProp = serializedObject.FindProperty("pythonScriptPath");
    }

    public override void OnInspectorGUI()
    {
        serializedObject.Update();

        EditorGUILayout.LabelField("Python Launcher Settings", EditorStyles.boldLabel);
        EditorGUILayout.Space();

        // Python Exe Path
        EditorGUILayout.BeginHorizontal();
        EditorGUILayout.PropertyField(pythonExePathProp, new GUIContent("Python Exe Path"));
        if (GUILayout.Button("Browse", GUILayout.Width(70)))
        {
            string path = EditorUtility.OpenFilePanel("Select Python Executable", "", "exe");
            if (!string.IsNullOrEmpty(path))
            {
                pythonExePathProp.stringValue = path;
            }
        }
        EditorGUILayout.EndHorizontal();

        // Python Script Path
        EditorGUILayout.BeginHorizontal();
        EditorGUILayout.PropertyField(pythonScriptPathProp, new GUIContent("Python Script Path"));
        if (GUILayout.Button("Browse", GUILayout.Width(70)))
        {
            string path = EditorUtility.OpenFilePanel("Select Python Script", "", "py");
            if (!string.IsNullOrEmpty(path))
            {
                pythonScriptPathProp.stringValue = path;
            }
        }
        EditorGUILayout.EndHorizontal();

        EditorGUILayout.Space();

        // Validation
        if (!string.IsNullOrEmpty(pythonExePathProp.stringValue) && !File.Exists(pythonExePathProp.stringValue))
        {
            EditorGUILayout.HelpBox("Python executable not found at specified path!", MessageType.Warning);
        }

        if (!string.IsNullOrEmpty(pythonScriptPathProp.stringValue) && !File.Exists(pythonScriptPathProp.stringValue))
        {
            EditorGUILayout.HelpBox("Python script not found at specified path!", MessageType.Warning);
        }

        serializedObject.ApplyModifiedProperties();
    }
}
