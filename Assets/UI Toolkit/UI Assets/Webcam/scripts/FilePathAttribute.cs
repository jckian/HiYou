#if UNITY_EDITOR
using UnityEngine;
using UnityEditor;

public class FilePathAttribute : PropertyAttribute 
{
    public string extension;

    public FilePathAttribute(string extension = "*")
    {
        this.extension = extension;
    }
}

[CustomPropertyDrawer(typeof(FilePathAttribute))]
public class FilePathDrawer : PropertyDrawer
{
    public override void OnGUI(Rect position, SerializedProperty property, GUIContent label)
    {
        EditorGUI.BeginProperty(position, label, property);

        Rect fieldRect = new Rect(position.x, position.y, position.width - 70, position.height);
        Rect buttonRect = new Rect(position.x + position.width - 65, position.y, 65, position.height);

        property.stringValue = EditorGUI.TextField(fieldRect, label, property.stringValue);

        if (GUI.Button(buttonRect, "Browse"))
        {
            var attr = (FilePathAttribute)attribute;

            string path = EditorUtility.OpenFilePanel(
                "Select File", 
                "", 
                attr.extension
            );

            if (!string.IsNullOrEmpty(path))
                property.stringValue = path;
        }

        EditorGUI.EndProperty();
    }
}
#endif
