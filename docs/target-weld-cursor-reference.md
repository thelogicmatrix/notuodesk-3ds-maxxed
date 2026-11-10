# Target Weld cursor evidence

Checked 10 November 2026. Scope is Editable Poly Target Weld at Vertex, Edge and Border levels.

## Grounded

1. [Autodesk 2026 Editable Poly (Vertex)](https://help.autodesk.com/cloudhelp/2026/ENU/3DSMax-Modeling/files/GUID-047B00EC-D4E3-4D05-8FB7-220795D13874.htm) says the pointer becomes a "+" over a vertex. After the first click, a dashed rubber-band line follows the pointer. Target Weld remains active until the button is clicked again or the viewport is right-clicked. Its Target Weld section contains no cursor or band image.
2. [Autodesk 2026 Editable Poly (Edge)](https://help.autodesk.com/cloudhelp/2026/ENU/3DSMax-Modeling/files/GUID-2C16FF31-BF20-450F-8163-3362A7037603.htm) explicitly describes a "+" over edges and an arrow away from them. Its Target Weld section contains no cursor or band image.
3. [Autodesk 2026 Basics of Selecting Objects](https://help.autodesk.com/cloudhelp/2026/ENU/3DSMax-Basics/files/GUID-1962BD49-AAD7-43FA-871E-5C2742C047B8.htm) calls the selectable-object pointer a small cross. Its [selection-preview screenshot](https://help.autodesk.com/cloudhelp/2026/ENU/3DSMax-Basics/images/GUID-4F999EB6-FF11-4A53-9652-448C5A517DC1.png) shows outlined cross arms and an open centre. The cursor is near (522,123) in the original 840x266 image. This is a general selection screenshot, not a Target Weld screenshot.
4. [Autodesk 2026 MAXScript Mouse Cursors](https://help.autodesk.com/cloudhelp/2026/ENU/MAXScript-Help/files/MAXScript-Tools-and-Interaction/Interacting-with-the-3ds-Max/Viewports/GUID-EE2C3ADF-9BAB-4424-AAAB-A5ABF027DE73.html) identifies the normal arrow and the standard Max system cursor names. It supplies no bitmap.

## Supporting evidence

- Aaron Czarnecki's [3DS Max 2016: Target Weld](https://www.youtube.com/watch?v=uwjGtz4iG3c), published 16 September 2016. Around 4:20.4, Target Weld is active and the hovered vertex has an outlined open-centre cross. Around 4:23.8 the pointer away from a vertex is an ordinary arrow. The downloaded 1280x720 stream is compressed. It cannot establish original cursor RGB values or Max 2026 DPI behaviour. Local reference files retain the original full frames and native-size crops.
- [Autodesk 2020 Editable Poly (Vertex)](https://help.autodesk.com/cloudhelp/2020/ENU/3DSMax-Modeling/files/GUID-047B00EC-D4E3-4D05-8FB7-220795D13874.htm) and [2016 Editable Poly (Edge)](https://help.autodesk.com/cloudhelp/2016/ENU/3DSMax/files/GUID-2C16FF31-BF20-450F-8163-3362A7037603.htm) repeat the arrow/plus descriptions. Their Target Weld sections also contain no cursor bitmap.
- The arrow asset is a capture of Windows normal-select resource IDC_ARROW (32512), requested at 32x32 with LoadImageW and rendered with DrawIconEx. The visible shape occupies 12x19 pixels, with hotspot (0,0). It is a system resource capture, not invented Max artwork. [Microsoft cursor identifiers](https://learn.microsoft.com/en-us/windows/win32/menurc/about-cursors) names IDC_ARROW as Normal select.

## What the implementation can claim

The POST_PIXEL overlay uses four separate cross arms with an open centre. At scale 1, the arm coordinates run from 3 to 7 pixels from the hotspot. A 3-pixel white stroke surrounds a 1-pixel black stroke. This construction follows the available screenshots. Those screenshots do not establish a lossless 2026 Target Weld cursor mask. The arrow uses the captured system artwork. Both drawings follow Blender's UI scale.

The band remains the pre-existing white line at alpha 0.95, with 5 pixels on and 5 off. Nathan confirmed that Max's band is dotted. No inspected source establishes its exact colour or interval, so the implementation does not change those values or claim a measured match.

## Captured comparison

The sandbox comparison includes native-size cursor crops and 3x inspection enlargements at effective Blender UI scales of 1.0 and 1.5. The 150% Max panels enlarge the source pixels with nearest-neighbour sampling. They are not native 150% Max captures.

Visible differences remain in the evidence. The recorded Max arrow and cross have soft, compressed edges. Blender's cross has crisp rectangular arm ends and a darker inner stroke. Its open centre exposes a blue Blender vertex marker in this fixture. The reference viewports have brown or textured backgrounds, while the fixture has a grey background. These captures cannot isolate the original Max cursor mask or settle its antialiasing. They do not establish pixel identity. No Max band panel can be supplied from the recovered sources.

## Unverified

Exact Max 2026 Target Weld bitmap, hotspot subpixel alignment, native antialiasing, colour values and DPI-specific cursor resources remain unverified. The 2016 recording and 2026 general selection image support the construction, but do not prove pixel identity. No direct Target Weld band reference was recovered. The comparisons label that missing reference instead of creating one.
