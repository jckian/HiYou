#if UNITY_EDITOR
using UnityEditor;
using UnityEngine;

public class FolderPathAttribute : PropertyAttribute { }

[CustomPropertyDrawer(typeof(FolderPathAttribute))]
public class FolderPathDrawer : PropertyDrawer
{
    public override void OnGUI(Rect position, SerializedProperty property, GUIContent label)
    {
        EditorGUI.BeginProperty(position, label, property);

        Rect fieldRect = new Rect(position.x, position.y, position.width - 70, position.height);
        Rect buttonRect = new Rect(position.x + position.width - 65, position.y, 65, position.height);

        property.stringValue = EditorGUI.TextField(fieldRect, label, property.stringValue);

        if (GUI.Button(buttonRect, "Browse"))
        {
            string path = EditorUtility.OpenFolderPanel("Select Folder", "", property.stringValue);
            if (!string.IsNullOrEmpty(path))
                property.stringValue = path;
        }

        EditorGUI.EndProperty();
    }
}
#endif
