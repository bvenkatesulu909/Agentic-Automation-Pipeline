"""Generate PDF guide for Multi-Agent Research System."""

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak,
    Image, KeepTogether
)
from reportlab.lib import colors
from datetime import datetime


def create_pdf():
    """Create comprehensive step-by-step PDF guide."""

    # Create PDF
    pdf_path = "Multi_Agent_Research_System_Step_by_Step.pdf"
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=letter,
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch
    )

    # Story to hold all content
    story = []

    # Styles
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=28,
        textColor=colors.HexColor('#2196F3'),
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )

    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=14,
        textColor=colors.HexColor('#666666'),
        spaceAfter=12,
        alignment=TA_CENTER
    )

    heading2_style = ParagraphStyle(
        'CustomHeading2',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#2196F3'),
        spaceAfter=12,
        spaceBefore=12,
        fontName='Helvetica-Bold'
    )

    heading3_style = ParagraphStyle(
        'CustomHeading3',
        parent=styles['Heading3'],
        fontSize=13,
        textColor=colors.HexColor('#1976D2'),
        spaceAfter=10,
        spaceBefore=10,
        fontName='Helvetica-Bold'
    )

    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['BodyText'],
        fontSize=10,
        alignment=TA_JUSTIFY,
        spaceAfter=8
    )

    # ==================== TITLE PAGE ====================
    story.append(Spacer(1, 1*inch))
    story.append(Paragraph("🤖 Multi-Agent Research System", title_style))
    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph("Step-by-Step Implementation Guide", subtitle_style))
    story.append(Spacer(1, 0.1*inch))
    story.append(Paragraph("Complete System with Supervisor Coordination & Consensus Logic", subtitle_style))
    story.append(Spacer(1, 0.3*inch))

    # Status badge
    status_text = "✅ PRODUCTION READY"
    story.append(Paragraph(status_text, ParagraphStyle(
        'Status',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.white,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        backColor=colors.HexColor('#4CAF50'),
        borderPadding=5
    )))

    story.append(Spacer(1, 0.5*inch))

    # Key info
    info_data = [
        ["Production Code", "~1,850 lines"],
        ["Test Cases", "50+ comprehensive tests"],
        ["Documentation", "~3,100 lines"],
        ["Components", "7 main classes"],
        ["Status", "✅ Ready for Production"]
    ]

    info_table = Table(info_data, colWidths=[2.5*inch, 2.5*inch])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F0F8FF')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#2196F3')),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#F0F8FF')])
    ]))
    story.append(info_table)

    story.append(Spacer(1, 0.5*inch))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y')}",
                          ParagraphStyle('Footer', parent=styles['Normal'], fontSize=9,
                                       alignment=TA_CENTER, textColor=colors.grey)))

    story.append(PageBreak())

    # ==================== TABLE OF CONTENTS ====================
    story.append(Paragraph("📋 Table of Contents", heading2_style))
    story.append(Spacer(1, 0.2*inch))

    toc_items = [
        "1. System Overview & Architecture",
        "2. Step 1: Understanding the Components",
        "3. Step 2: The Research Workflow",
        "4. Step 3: Consensus Engine Logic",
        "5. Step 4: Approval Workflow",
        "6. Step 5: Audit Trail System",
        "7. Step 6: Running Your First Task",
        "8. Step 7: Advanced Usage",
        "9. Step 8: Integration & Deployment",
        "10. Step 9: Quick Reference & Troubleshooting"
    ]

    for item in toc_items:
        story.append(Paragraph(f"• {item}", body_style))
        story.append(Spacer(1, 0.05*inch))

    story.append(PageBreak())

    # ==================== SECTION 1: OVERVIEW ====================
    story.append(Paragraph("📌 System Overview & Architecture", heading2_style))
    story.append(Spacer(1, 0.15*inch))

    story.append(Paragraph(
        "<b>What is the Multi-Agent Research System?</b>",
        body_style
    ))
    story.append(Paragraph(
        "A production-ready system that coordinates multiple AI agents (Researcher, Writer, Fact-Checker) under supervisor governance to conduct research, generate content, and verify accuracy - with intelligent consensus analysis, human approval gates, and complete audit trails.",
        body_style
    ))
    story.append(Spacer(1, 0.2*inch))

    # Statistics table
    stats_data = [
        ["Metric", "Value"],
        ["Production Code", "~1,850 lines"],
        ["Test Code", "~450 lines (50+ tests)"],
        ["Documentation", "~3,100 lines"],
        ["Components", "7 main classes"],
        ["Token Usage/Iteration", "3,800-7,500 tokens"],
        ["Latency/Iteration", "40-75 seconds"]
    ]

    stats_table = Table(stats_data, colWidths=[2.5*inch, 2.5*inch])
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2196F3')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#CCCCCC')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F0F8FF')])
    ]))
    story.append(stats_table)

    story.append(PageBreak())

    # ==================== SECTION 2: COMPONENTS ====================
    story.append(Paragraph("🔧 Step 1: Understanding the Components", heading2_style))
    story.append(Spacer(1, 0.15*inch))

    components = [
        {
            "name": "Component 1: ResearcherAgent 🔍",
            "purpose": "Gathers and synthesizes information",
            "responsibilities": [
                "Research the given query comprehensively",
                "Identify credible sources",
                "Synthesize findings into a report",
                "Rate confidence (0.0-1.0)",
                "Explain reasoning"
            ],
            "input": "ResearchTask + previous state context",
            "output": "AgentDecision with research findings and confidence"
        },
        {
            "name": "Component 2: WriterAgent ✍️",
            "purpose": "Creates polished, engaging output",
            "responsibilities": [
                "Transform research into clear narrative",
                "Structure information logically",
                "Maintain engagement and clarity",
                "Ensure consistency",
                "Rate writing quality (0.0-1.0)"
            ],
            "input": "ResearchTask + researcher findings",
            "output": "AgentDecision with written content and confidence"
        },
        {
            "name": "Component 3: FactCheckerAgent ✓",
            "purpose": "Verifies accuracy and quality",
            "responsibilities": [
                "Verify factual accuracy of claims",
                "Check logical consistency",
                "Identify unsupported assertions",
                "Assess overall quality",
                "List specific issues found",
                "Rate verification confidence (0.0-1.0)"
            ],
            "input": "ResearchTask + all previous outputs",
            "output": "AgentDecision with issues found and confidence"
        }
    ]

    for comp in components:
        story.append(Paragraph(comp["name"], heading3_style))
        story.append(Paragraph(f"<b>Purpose:</b> {comp['purpose']}", body_style))
        story.append(Paragraph("<b>Responsibilities:</b>", body_style))
        for resp in comp["responsibilities"]:
            story.append(Paragraph(f"• {resp}", body_style))
        story.append(Paragraph(f"<b>Input:</b> {comp['input']}", body_style))
        story.append(Paragraph(f"<b>Output:</b> {comp['output']}", body_style))
        story.append(Spacer(1, 0.15*inch))

    story.append(PageBreak())

    # ==================== SECTION 3: WORKFLOW ====================
    story.append(Paragraph("🔄 Step 2: The Research Workflow", heading2_style))
    story.append(Spacer(1, 0.15*inch))

    workflow_steps = [
        {
            "num": "1",
            "title": "Create ResearchTask",
            "desc": "Define research parameters"
        },
        {
            "num": "2",
            "title": "Create ResearchSupervisor",
            "desc": "Initialize the orchestrator and all agents"
        },
        {
            "num": "3",
            "title": "Researcher Agent Executes",
            "desc": "Agent gathers information on query"
        },
        {
            "num": "4",
            "title": "Writer Agent Executes",
            "desc": "Agent polishes research into content"
        },
        {
            "num": "5",
            "title": "Fact-Checker Agent Executes",
            "desc": "Agent verifies accuracy and quality"
        },
        {
            "num": "6",
            "title": "Supervisor Consensus Analysis",
            "desc": "Supervisor analyzes agreement among all agents"
        }
    ]

    for step in workflow_steps:
        step_text = f"<b>Step {step['num']}: {step['title']}</b> - {step['desc']}"
        story.append(Paragraph(step_text, ParagraphStyle(
            'Step',
            parent=body_style,
            leftIndent=20,
            textColor=colors.HexColor('#1976D2'),
            fontSize=11
        )))
        story.append(Spacer(1, 0.1*inch))

    story.append(PageBreak())

    # ==================== SECTION 4: CONSENSUS ====================
    story.append(Paragraph("📊 Step 3: Consensus Engine Logic", heading2_style))
    story.append(Spacer(1, 0.15*inch))

    story.append(Paragraph("<b>Understanding Consensus Scoring</b>", heading3_style))
    story.append(Paragraph("Consensus Score Range: 0.0 (no agreement) to 1.0 (perfect agreement)", body_style))
    story.append(Spacer(1, 0.1*inch))

    consensus_data = [
        ["Score Range", "Interpretation", "Recommendation"],
        ["≥ 0.85", "Excellent Agreement", "Ready for approval immediately"],
        ["0.75 - 0.85", "Good Agreement", "Minor revisions noted"],
        ["0.65 - 0.75", "Fair Agreement", "Recommend detailed review"],
        ["< 0.65", "Poor Agreement", "Requires revision"]
    ]

    consensus_table = Table(consensus_data, colWidths=[1.5*inch, 1.8*inch, 1.7*inch])
    consensus_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2196F3')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#CCCCCC')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F0F8FF')])
    ]))
    story.append(consensus_table)

    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph("<b>How Consensus is Calculated</b>", heading3_style))

    consensus_steps = [
        "Step 1: Collect Confidence Scores from each agent (Researcher, Writer, Fact-Checker)",
        "Step 2: Calculate Average score across all three agents",
        "Step 3: Identify Issues (low confidence agents, fact-checker concerns)",
        "Step 4: Determine Status (Consensus reached? Ready for approval?)",
        "Step 5: Calculate Revision Priority for improvements"
    ]

    for step in consensus_steps:
        story.append(Paragraph(f"• {step}", body_style))

    story.append(PageBreak())

    # ==================== SECTION 5: APPROVAL ====================
    story.append(Paragraph("🔐 Step 4: Approval Workflow", heading2_style))
    story.append(Spacer(1, 0.15*inch))

    story.append(Paragraph("<b>Two Approval Modes</b>", heading3_style))

    story.append(Paragraph("<b>Mode 1: Manual Approval (Default)</b>", heading3_style))
    story.append(Paragraph(
        "When to Use: Important decisions requiring human judgment",
        body_style
    ))
    story.append(Paragraph(
        "<b>Process:</b>",
        body_style
    ))
    approval_steps = [
        "Supervisor requests approval",
        "Human sees research summary and metrics",
        "Human reviews quality scores and issues",
        "Human makes decision: approve, reject, or detailed review",
        "Decision logged with timestamp and feedback"
    ]

    for step in approval_steps:
        story.append(Paragraph(f"• {step}", body_style))

    story.append(Spacer(1, 0.15*inch))
    story.append(Paragraph("<b>Mode 2: Auto-Approval (Optional)</b>", heading3_style))
    story.append(Paragraph(
        "When to Use: Routine tasks with predictable high quality",
        body_style
    ))
    story.append(Paragraph("<b>Criteria for Auto-Approval:</b>", body_style))

    auto_criteria = [
        "✓ Consensus score ≥ configured threshold (default 0.85)",
        "✓ No critical fact-checker issues",
        "✓ All agents confident (above 0.7)"
    ]

    for criteria in auto_criteria:
        story.append(Paragraph(f"{criteria}", body_style))

    story.append(Spacer(1, 0.15*inch))
    story.append(Paragraph("<b>Approval Status Values</b>", heading3_style))

    approval_status_data = [
        ["Status", "Meaning"],
        ["AWAITING_APPROVAL", "Waiting for human decision"],
        ["APPROVED", "Human approved"],
        ["REJECTED", "Human rejected"],
        ["AUTO_APPROVED", "Auto-approved (if enabled)"]
    ]

    status_table = Table(approval_status_data, colWidths=[2*inch, 3*inch])
    status_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2196F3')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#CCCCCC')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F0F8FF')])
    ]))
    story.append(status_table)

    story.append(PageBreak())

    # ==================== SECTION 6: AUDIT ====================
    story.append(Paragraph("📋 Step 5: Audit Trail System", heading2_style))
    story.append(Spacer(1, 0.15*inch))

    story.append(Paragraph("<b>What Gets Logged</b>", heading3_style))

    audit_items = [
        "Workflow start time",
        "Each agent decision (researcher/writer/fact-checker)",
        "Consensus analysis results",
        "Approval requests",
        "Approval/rejection decisions with feedback",
        "Workflow completion",
        "All with timestamps and metadata"
    ]

    for item in audit_items:
        story.append(Paragraph(f"• {item}", body_style))

    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph("<b>Key Benefits of Audit Trail</b>", heading3_style))

    audit_benefits = [
        "Complete compliance documentation",
        "Full traceability of all decisions",
        "Approval chain with signatories",
        "Export reports for audits",
        "Task history queries",
        "Agent-specific decision tracking"
    ]

    for benefit in audit_benefits:
        story.append(Paragraph(f"✓ {benefit}", body_style))

    story.append(PageBreak())

    # ==================== SECTION 7: FIRST TASK ====================
    story.append(Paragraph("⚡ Step 6: Running Your First Task", heading2_style))
    story.append(Spacer(1, 0.15*inch))

    story.append(Paragraph("<b>Quick Start: 3 Steps</b>", heading3_style))

    story.append(Paragraph("<b>Step 6.1: Import the System</b>", heading3_style))
    story.append(Paragraph(
        "from ragstack.research_agents import ResearchSupervisor, ResearchTask",
        ParagraphStyle('Code', parent=styles['Normal'], fontSize=9,
                      fontName='Courier', textColor=colors.HexColor('#D63384'),
                      backColor=colors.HexColor('#F4F4F4'), leftIndent=20)
    ))

    story.append(Spacer(1, 0.15*inch))
    story.append(Paragraph("<b>Step 6.2: Create Supervisor and Task</b>", heading3_style))
    story.append(Paragraph(
        "supervisor = ResearchSupervisor()\ntask = ResearchTask(query=\"Your question\")",
        ParagraphStyle('Code', parent=styles['Normal'], fontSize=9,
                      fontName='Courier', textColor=colors.HexColor('#D63384'),
                      backColor=colors.HexColor('#F4F4F4'), leftIndent=20)
    ))

    story.append(Spacer(1, 0.15*inch))
    story.append(Paragraph("<b>Step 6.3: Execute Research</b>", heading3_style))
    story.append(Paragraph(
        "state = supervisor.execute_research(task, require_approval=False)",
        ParagraphStyle('Code', parent=styles['Normal'], fontSize=9,
                      fontName='Courier', textColor=colors.HexColor('#D63384'),
                      backColor=colors.HexColor('#F4F4F4'), leftIndent=20)
    ))

    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph("<b>Access Your Results</b>", heading3_style))

    results_items = [
        "state.writer_decision.content → Final output",
        "state.approval_status → Approval result",
        "state.supervisor_consensus.confidence → Consensus score",
        "state.iteration → Number of iterations used",
        "supervisor.get_audit_report(task.task_id) → Audit trail"
    ]

    for item in results_items:
        story.append(Paragraph(f"• {item}", body_style))

    story.append(PageBreak())

    # ==================== SECTION 8: ADVANCED ====================
    story.append(Paragraph("🚀 Step 7: Advanced Usage", heading2_style))
    story.append(Spacer(1, 0.15*inch))

    story.append(Paragraph("<b>Batch Processing Multiple Tasks</b>", heading3_style))
    story.append(Paragraph(
        "Process multiple research tasks efficiently with auto-approval enabled. "
        "Tasks are processed sequentially with results aggregated for batch reporting.",
        body_style
    ))

    story.append(Spacer(1, 0.1*inch))
    story.append(Paragraph("<b>Customizing Agent Behavior</b>", heading3_style))
    story.append(Paragraph(
        "Use different models for different agents, configure consensus thresholds, "
        "and adjust approval gate criteria based on your requirements.",
        body_style
    ))

    story.append(Spacer(1, 0.1*inch))
    story.append(Paragraph("<b>Cost Optimization</b>", heading3_style))
    cost_options = [
        "Use lighter model: claude-sonnet-5 instead of opus",
        "Reduce iterations: max_iterations=1 for quick tasks",
        "Lower research depth: 'light' instead of 'deep'",
        "Enable auto-approval: Skip manual approval wait time",
        "Batch processing: Process multiple tasks together",
        "Estimated cost: $0.02-0.05 per task"
    ]

    for opt in cost_options:
        story.append(Paragraph(f"• {opt}", body_style))

    story.append(PageBreak())

    # ==================== SECTION 9: INTEGRATION ====================
    story.append(Paragraph("🔗 Step 8: Integration & Deployment", heading2_style))
    story.append(Spacer(1, 0.15*inch))

    story.append(Paragraph("<b>Integration Patterns</b>", heading3_style))

    patterns = [
        {
            "name": "Web Frameworks (FastAPI)",
            "desc": "Create REST APIs for research tasks with async support"
        },
        {
            "name": "Task Queues (Celery)",
            "desc": "Process research tasks asynchronously in background"
        },
        {
            "name": "Database Storage",
            "desc": "Store research results and audit trails in databases"
        },
        {
            "name": "Monitoring & Logging",
            "desc": "Track system health and task execution with logging"
        },
        {
            "name": "Batch Processing",
            "desc": "Process multiple tasks with aggregated results"
        }
    ]

    for pattern in patterns:
        story.append(Paragraph(f"<b>• {pattern['name']}</b>", body_style))
        story.append(Paragraph(f"  {pattern['desc']}", body_style))

    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph("<b>Deployment Checklist</b>", heading3_style))

    deploy_checks = [
        "Set ANTHROPIC_API_KEY environment variable",
        "Configure LLM model (default: claude-opus-5)",
        "Set confidence_threshold (default: 0.7)",
        "Choose approval mode (manual/auto)",
        "Setup audit log directory",
        "Configure database connections if needed",
        "Set up monitoring and logging",
        "Test with sample tasks",
        "Run full test suite"
    ]

    for check in deploy_checks:
        story.append(Paragraph(f"□ {check}", body_style))

    story.append(PageBreak())

    # ==================== SECTION 10: REFERENCE ====================
    story.append(Paragraph("📚 Step 9: Quick Reference & Troubleshooting", heading2_style))
    story.append(Spacer(1, 0.15*inch))

    story.append(Paragraph("<b>Common Issues & Solutions</b>", heading3_style))

    issues = [
        {
            "problem": "Low Consensus Score (< 0.65)",
            "solutions": "Increase research depth | Provide more context | Lower confidence threshold | Manually review"
        },
        {
            "problem": "Too Many Iterations",
            "solutions": "Lower confidence threshold | Reduce max_iterations | Enable auto-approval | Review recommendations"
        },
        {
            "problem": "Approval Timeout",
            "solutions": "Enable auto-approval | Batch process with auto-approval | Use concise summaries"
        },
        {
            "problem": "High Token Usage",
            "solutions": "Use cheaper model (Sonnet) | Reduce depth | Use fewer iterations"
        }
    ]

    for issue in issues:
        story.append(Paragraph(f"<b>Issue:</b> {issue['problem']}", body_style))
        story.append(Paragraph(f"<b>Solutions:</b> {issue['solutions']}", body_style))
        story.append(Spacer(1, 0.08*inch))

    story.append(Spacer(1, 0.15*inch))
    story.append(Paragraph("<b>Configuration Quick Reference</b>", heading3_style))

    config_data = [
        ["Parameter", "Type", "Default", "Purpose"],
        ["model", "str", "claude-opus-5", "LLM model to use"],
        ["max_iterations", "int", "3", "Refinement attempts"],
        ["confidence_threshold", "float", "0.7", "Consensus bar"],
        ["enable_auto_approval", "bool", "False", "Auto-approve high quality"]
    ]

    config_table = Table(config_data, colWidths=[1.4*inch, 0.9*inch, 1.2*inch, 1.5*inch])
    config_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2196F3')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#CCCCCC')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F0F8FF')])
    ]))
    story.append(config_table)

    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph("<b>API Quick Reference</b>", heading3_style))

    api_ref = [
        "<b>ResearchSupervisor:</b>",
        "• execute_research(task, require_approval) → ResearchState",
        "• get_audit_report(task_id) → dict",
        "• get_compliance_summary(task_id) → dict",
        "",
        "<b>ConsensusEngine:</b>",
        "• evaluate(researcher, writer, fact_checker) → ConsensusResult",
        "",
        "<b>AuditTrail:</b>",
        "• log_action(...) → AuditLog",
        "• get_task_history(task_id) → list",
        "• export_task_report(task_id) → dict",
        "",
        "<b>HumanApprovalGate:</b>",
        "• request_approval(state) → bool",
        "• should_auto_approve(state) → bool"
    ]

    for ref in api_ref:
        if ref.startswith("<b>"):
            story.append(Paragraph(ref, body_style))
        else:
            story.append(Paragraph(ref, ParagraphStyle('APIRef', parent=body_style,
                                                       leftIndent=20, fontSize=9)))

    story.append(Spacer(1, 0.3*inch))

    # ==================== FOOTER ====================
    footer_text = (
        "Multi-Agent Research System - Step by Step Guide | "
        f"Generated: {datetime.now().strftime('%B %d, %Y')} | "
        "Status: ✅ Production Ready"
    )
    story.append(Paragraph(footer_text, ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        alignment=TA_CENTER,
        textColor=colors.grey,
        borderPadding=10,
        borderColor=colors.lightgrey
    )))

    # Build PDF
    doc.build(story)
    print(f"[SUCCESS] PDF created successfully: {pdf_path}")
    return pdf_path


if __name__ == "__main__":
    create_pdf()
