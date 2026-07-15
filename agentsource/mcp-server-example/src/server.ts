import express from "express";

// Minimal MCP-style HTTP server: implements just enough of the MCP "tools/list" and
// "tools/call" contract (see docs/LLD.md section 4) to demonstrate the pattern without
// pulling in a full MCP SDK. Swap in the official SDK before treating this as production code.

const app = express();
app.use(express.json());

const TOOL_NAME = "example_mcp_tool";

app.post("/mcp/tools/list", (_req, res) => {
  res.json({
    tools: [
      {
        name: TOOL_NAME,
        description: "Returns a static example payload for a given key.",
        inputSchema: {
          type: "object",
          required: ["key"],
          properties: { key: { type: "string" } },
        },
      },
    ],
  });
});

app.post("/mcp/tools/call", (req, res) => {
  const { name, arguments: args } = req.body ?? {};
  if (name !== TOOL_NAME) {
    return res.status(404).json({ error: "unknown_tool", message: `No tool named ${name}` });
  }
  res.json({
    output: {
      key: args?.key ?? null,
      items: [
        { id: "item-1", description: "Example item one", required: true },
        { id: "item-2", description: "Example item two", required: false },
      ],
    },
  });
});

const port = process.env.PORT ? Number(process.env.PORT) : 7100;
app.listen(port, () => {
  console.log(`mcp-server-example listening on :${port}`);
});
