import ast
import operator

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.operand))
    raise ValueError(f"Unsupported expression element: {ast.dump(node)}")


def evaluate(expression: str) -> float:
    """Safely evaluate an arithmetic expression — no names, calls, or attribute access allowed."""
    tree = ast.parse(expression, mode="eval")
    return _eval_node(tree.body)


NAME = "calculator"
DESCRIPTION = "Evaluates a basic arithmetic expression (+, -, *, /, %, **, parentheses)."
INPUT_SCHEMA = {
    "type": "object",
    "properties": {"expression": {"type": "string"}},
    "required": ["expression"],
}
OUTPUT_SCHEMA = {"type": "object", "properties": {"result": {"type": "number"}}}


def run(args: dict, context: dict | None = None) -> dict:
    return {"result": evaluate(args["expression"])}
