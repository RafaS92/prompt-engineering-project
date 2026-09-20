Draft the customer response for this resolved support ticket.

<support_ticket>
{{ ticket_text | xml_escape }}
</support_ticket>

<triage_result>
{{ triage_result | xml_escape }}
</triage_result>

<policy_decision>
{{ policy_decision | xml_escape }}
</policy_decision>

<support_policies>
{{ support_policies | xml_escape }}
</support_policies>
