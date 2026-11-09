# Historical primitive fixture

`pre-rewrite-primitives.blend` is the genuine saved-scene fixture supplied by the
wave-1 reviewer for F3. The reviewer created it with the pre-rewrite package at
`be256d8`, through its public creation and parameter routes. It contains nine
standard primitive kinds, with radius1 2, radius2 0.5, height 3, length 4 and
width 5 where applicable.

The clean-side fix copied this data file without reading historical source.
Tests append its mesh objects or load it with script execution disabled.
