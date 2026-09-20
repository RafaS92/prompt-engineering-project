Determine the policy outcome for this support ticket.

<support_ticket>
{{ ticket_text | xml_escape }}
</support_ticket>

<triage_result>
{{ triage_result | xml_escape }}
</triage_result>

<support_policies>
{{ support_policies | xml_escape }}
</support_policies>
