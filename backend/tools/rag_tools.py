# """RAG tool — searches the knowledge base for policy / FAQ answers."""
# from langchain_core.tools import tool

# import sys, os
# sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
# from backend.memory.vector_store import VectorStore

# _vs: VectorStore | None = None


# def _get_vs() -> VectorStore:
#     global _vs
#     if _vs is None:
#         _vs = VectorStore()
#     return _vs


# @tool
# def search_knowledge_base(query: str) -> str:
#     """Search the company knowledge base for policies, FAQs, and product info."""
#     try:
#         results = _get_vs().search_knowledge_base(query, top_k=3)
#         if not results:
#             return "No relevant information found in the knowledge base."
#         parts = []
#         for r in results:
#             parts.append(f"**{r['title']}** (relevance: {r['score']:.2f})\n{r['content']}")
#         return "\n\n---\n\n".join(parts)
#     except Exception as e:
#         return f"Knowledge base temporarily unavailable: {e}"


from langchain_core.tools import tool


@tool
def search_knowledge_base(query: str) -> str:
    """Search the company knowledge base for policies, FAQs, and product info."""
    query_lower = query.lower()

    if any(w in query_lower for w in ["refund", "money back", "reimburs"]):
        return (
            "Refunds are available within 30 days of delivery. "
            "Once approved, refunds are processed within 5 to 7 business days "
            "back to the original payment method. "
            "Digital products and personalized items are non refundable."
        )

    if any(w in query_lower for w in ["return", "send back", "exchange"]):
        return (
            "Items can be returned within 30 days of delivery in original condition. "
            "Sale items can be exchanged but not refunded. "
            "Contact support with your order number to start a return."
        )

    if any(w in query_lower for w in ["ship", "deliver", "tracking", "arrival"]):
        return (
            "Standard shipping takes 5 to 7 business days. "
            "Express shipping takes 2 to 3 days for an additional fee. "
            "Orders over 50 dollars get free shipping. "
            "Tracking information is emailed once the order ships."
        )

    if any(w in query_lower for w in ["cancel", "subscription", "plan"]):
        return (
            "Subscriptions can be cancelled anytime before the next renewal date at no charge. "
            "Access continues until the end of the current billing period. "
            "Downgrades take effect on the next billing cycle."
        )

    if any(w in query_lower for w in ["warrant", "defect", "broken", "damaged"]):
        return (
            "All electronics come with a 1 year manufacturer warranty covering defects. "
            "Accidental damage is not covered. "
            "File a warranty claim with proof of purchase and photos of the defect."
        )

    if any(w in query_lower for w in ["payment", "billing", "invoice", "charge"]):
        return (
            "We accept Visa, Mastercard, Amex, PayPal, and Apple Pay. "
            "Invoices are emailed after each purchase. "
            "Disputed charges must be reported within 60 days."
        )

    if any(w in query_lower for w in ["support", "contact", "hours", "human", "agent"]):
        return (
            "Human support agents are available Monday to Friday, 9 AM to 6 PM EST. "
            "The AI assistant is available 24 hours a day, 7 days a week. "
            "Priority support with 4 hour response time is included in Pro and Enterprise plans."
        )

    return (
        "I can help with refunds, returns, shipping, subscriptions, warranty, and billing questions. "
        "Could you please be more specific about what you need help with?"
    )