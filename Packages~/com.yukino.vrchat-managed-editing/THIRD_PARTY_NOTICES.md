# Attribution and dependency notices

## UnityAgent

The phase-1 workflow learns from BlendShapeTools, FaceProfileTools and the
expression-preview/confirmation concepts in https://github.com/lighfu/unity-agent,
commit `347f054a0c934c3ee14b0568968cd269726de323` (AjisaiFlow, MIT).
The original general-purpose dispatcher, credentials, arbitrary C#/reflection,
file tools, upload tools, fuzzy-name setters and reset-all behavior are NOT ported.
The local scope policy and restrictive bridge are new implementations.

The upstream license is preserved below:

```text
MIT License

Copyright (c) 2025-2026 AjisaiFlow

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## CoplayDev MCP for Unity

This optional package uses the public C# tool attribute/handler contract of
https://github.com/CoplayDev/unity-mcp, version `10.2.0`. It depends on that package
and Newtonsoft JSON `3.0.2`; their binaries and Unity editor binaries are not
bundled here. Consult those dependencies for their licenses.
