using UnityEngine;
using UnityEngine.UIElements;
using System.Collections;
using System.Collections.Generic;
public class SceneSwitcherSample : MonoBehaviour
{
    // Start is called once before the first execution of Update after the MonoBehaviour is created
    void Start()
    {
        
    }

    public UIDocument scene1;
    public UIDocument scene3;

    // Update is called once per frame
    void Update()
    {
       if (Time.frameCount % 1200 == 0)
        {
            scene1.enabled = !scene1.enabled;
            scene3.enabled = !scene1.enabled;
        }
        
    }
}
