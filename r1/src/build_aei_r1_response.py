from __future__ import annotations

import re
import shutil
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt


ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "data" / "review" / "Comments_for_author.txt"
TEMPLATE = Path(r"E:\论文\工作内论文\Information Processing & Management\修改R1\Response_to_reviewers.docx")
SUBMIT = ROOT.parent / "提交_AEI_R1"
ARTICLE = ROOT / "article"


def extract_comments() -> tuple[str, list[str], str, list[str], str, list[str]]:
    lines = REVIEW.read_text(encoding="utf-8").splitlines()
    r1_line = next(line for line in lines if line.startswith("Reviewer #1:"))
    r1 = [r1_line.split("Reviewer #1: ", 1)[1]]
    r1.extend(line.strip() for line in lines[34:35])
    r2_line = next(line for line in lines if line.startswith("Reviewer #2:"))
    r2_overall = r2_line.split("Reviewer #2: ", 1)[1]
    r2 = [line.strip() for line in lines[38:48] if line.strip()]
    r3_line = next(line for line in lines if line.startswith("Reviewer #3:"))
    r3_overall = r3_line.split("Reviewer #3: ", 1)[1]
    r3 = [line.strip() for line in lines[52:68] if line.strip()]
    if len(r1) != 2 or len(r2) != 10 or len(r3) != 16:
        raise RuntimeError(f"Unexpected review structure: {len(r1)}, {len(r2)}, {len(r3)}")
    return r1[0], r1, r2_overall, r2, r3_overall, r3


R1_RESPONSE_EN = [
    (
        "Thank you for identifying this boundary condition. We agree that the contribution should be evaluated against reproducible non-language-model interfaces as well as against language-model outputs. We will add a controlled comparison with a predefined electronic form, a JavaScript Object Notation schema with constrained generation, a function-calling interface, a finite-state workflow, and a stronger deterministic parser. All alternatives will use the same request fields, admissibility rules, and test cases. We will report request accuracy, clarification rate, execution errors, latency, computational and service cost, and maintenance effort. The revised text will separate the contribution of structured request interpretation from the contribution of the deterministic validation layer.",
        "Sections 2–5 and Supplementary Material: alternative interfaces, parser specification, evaluation protocol, and matched comparison tables.",
    ),
    (
        "We appreciate this important reminder about the planning objective. We agree that a reserve policy should satisfy a stated reliability requirement before cost is interpreted. We will make the empirical coverage threshold an explicit feasibility condition, report the admissible policies at a common threshold, and compare mean cost and conditional value at risk only after this screening. The manuscript will explain that a higher procurement cost can be the direct consequence of enforcing the reliability requirement. This change will also clarify the role of the reserve calibration module in the end-to-end study.",
        "Sections 3–6 and Supplementary Material: coverage constraint, policy screening, cost comparison, and sensitivity analysis.",
    ),
]


R2_RESPONSE_EN = [
    (
        "We thank you for this detailed assessment of the manuscript. We will use the specific points below to separate the request-validation study from the reserve-calibration study, strengthen the benchmark design, and narrow claims to the evidence supported by the experiments.",
        "Opening response to the overall assessment; detailed changes are recorded in the numbered replies below.",
    ),
    (
        "Thank you for requesting a stronger comparison. We agree that deterministic validation can be implemented through several structured interfaces. We will evaluate the proposed workflow against a predefined form, schema-constrained generation, a function-calling interface, a finite-state workflow, and a stronger deterministic parser under identical field requirements and validation rules. The comparison will report accuracy, clarification rate, execution errors, latency, service and computational cost, and maintenance effort. The manuscript will describe the word-matching parser as a baseline component and will identify which safety effects arise from the fixed validation layer.",
        "Sections 2–5 and Supplementary Material: alternative interfaces and matched evaluation results.",
    ),
    (
        "We appreciate this concern about benchmark independence and agree that benchmark construction must be documented separately from rule design. We will report annotator number, expertise, instructions, independent double annotation, agreement statistics, disagreement resolution, class distribution, and the generation process for each request set. We will add an independently annotated evaluation set containing paraphrases, typographical errors, multilingual ambiguity, prompt-injection attempts, and multi-turn corrections. The deployment statement will be limited to the request types represented by the verified evaluation data.",
        "Section 3, Section 5, and Supplementary Material: benchmark construction, annotation protocol, agreement analysis, and independent evaluation set.",
    ),
    (
        "We agree that one response per request does not characterize stochastic service behavior. We will repeat each service–request evaluation under documented decoding settings and archive the model identifier, application programming interface version, system prompt, date, temperature, sampling parameters, token counts, latency, and service cost. We will report means, confidence intervals, failure consistency, pairwise comparisons, and multiplicity-adjusted significance results. The reproducibility package will retain these records so that the reported service comparison remains auditable after service updates.",
        "Sections 3 and 5, Section 7, and Supplementary Material: repeated-run protocol, uncertainty estimates, metadata archive, and cost accounting.",
    ),
    (
        "Thank you for distinguishing keyword blocking from semantic resolution. We agree that the unresolved-default check should be interpreted as a deterministic safety gate. We will report false-clarification and missed-ambiguity rates, add implicit-ambiguity cases without trigger words, and evaluate a complete clarification loop in which the answer is incorporated into the request and checked again. The 14 eligible requests that currently remain unresolved will receive a separate failure analysis covering the missing field, clarification turn, final disposition, and reason for non-completion.",
        "Sections 4–6 and Supplementary Material: ambiguity taxonomy, multi-turn clarification experiment, and unresolved-case analysis.",
    ),
    (
        "We accept this recommendation. The Discussion will be reorganized around three linked findings: information-boundary enforcement, the operational trade-off between clarification and completion, and reserve calibration under a stated reliability requirement. Each interpretation will be tied to the corresponding experiment, with the deterministic validation result and the numerical reserve result kept distinct. The revised Discussion will state which observations are empirical and which are methodological implications.",
        "Section 7: revised Discussion structure and interpretation of the main findings.",
    ),
    (
        "We appreciate the request to strengthen the methodological context. We will add recent, verifiable studies on optimization-assisted energy forecasting, nonlinear uncertainty modeling, and intelligent decision and control systems. The new discussion will connect nonlinear time-series representation, optimization-guided forecasting, uncertainty-sensitive decision support, and robust control under changing operating conditions to the information-boundary problem studied here. All added references will be checked for bibliographic accuracy and relevance to the claims they support.",
        "Section 2: expanded related work and verified references.",
    ),
    (
        "We agree that the link between request validation and reserve performance needs a direct trace. We will construct a request-perturbation matrix in which region, horizon, admissible variables, cost ratio, reliability target, and reporting requirements are varied independently and in selected combinations. Each accepted plan will be linked to the exact calculation input and output that it changes. We will quantify the operational consequences of incorrect, incomplete, clarified, and correctly accepted plans. The revised manuscript will state explicitly that reserve cost and coverage are produced by the numerical calibration method, while the validation layer determines whether the requested calculation is admissible and sufficiently specified.",
        "Sections 3–6 and Supplementary Material: request-to-calculation traceability and end-to-end perturbation analysis.",
    ),
    (
        "Thank you for the statistical clarification. We agree that overlapping targets, shared rolling histories, adaptive state selection, and coverage screening do not support a formal finite-sample conformal guarantee in the present setting. We will describe the reported value as empirical rolling-window coverage, analyze temporal dependence, and report sensitivity to calibration length, neighborhood size, effective sample size, shrinkage selection, and coverage-screening thresholds. Where feasible, we will add block or sequential calibration analyses. The conclusion will avoid presenting the empirical value as a theoretical guarantee.",
        "Sections 3, 5–7, and Supplementary Material: dependence-aware calibration, sensitivity analysis, and claim boundaries.",
    ),
    (
        "We agree that reproducibility and external validity require clearer data documentation. We will add a fully public high-resolution validation dataset, exact preprocessing and missing-data rules, spatially appropriate weather inputs, and normalized quantities with a physical interpretation wherever the public data permit it. The anonymized primary dataset will be described with its permitted aggregate information, while claims about monetary or market performance will be limited to normalized study costs unless reserve prices and imbalance penalties are directly available. The external-validity discussion will distinguish the public validation setting from the primary regional analysis.",
        "Sections 3, 5, and 7, Data and code availability statement, and Supplementary Material: public validation data and preprocessing record.",
    ),
    (
        "We accept this recommendation. All reserve policies will be screened against a common empirical coverage requirement before cost and conditional value at risk are compared. We will document predictor architectures, hyperparameter selection, scenario construction, uncertainty sets, and computational budgets. The resource-allocation example will be labelled as illustrative and its omitted network and market constraints will be stated as scope conditions. We will also simplify the figures so that the decision boundary and the request-to-calculation connection remain visible at normal reading size.",
        "Sections 3–7 and Supplementary Material: common-constraint comparison, computational details, scope conditions, and revised figures.",
    ),
]


R3_RESPONSE_EN = [
    (
        "We thank you for the careful reading of the study boundary. We agree that the 200-request blind set is synthetic because it was generated after the validation rules were frozen. We will state this explicitly, add an independently authored or independently annotated test set where available, and restrict deployment language to the validated request classes. The manuscript will distinguish rule-frozen synthetic evaluation from evidence of performance on operational requests.",
        "Sections 3, 5, and 7: blind-set provenance, independent evaluation, and deployment boundary.",
    ),
    (
        "We appreciate this reproducibility requirement. We will permanently archive the identifiers of the DeepSeek, Qwen, ERNIE, and Hunyuan services, request dates, decoding parameters, system prompts, application programming interface versions, and response records. The archive will be linked to the request-level evaluation table and will record any service change encountered during the revision experiments.",
        "Section 3, Section 7, and the reproducibility package: service metadata and version records.",
    ),
    (
        "We agree that repeated execution is needed to characterize stochasticity. We will run multiple independent repetitions for every service and request, preserve all responses, and report the distribution of joint success, accept, reject, and clarify outcomes together with uncertainty intervals. The single-response results will no longer be presented as a robustness assessment.",
        "Sections 3 and 5 and Supplementary Material: repeated-run design and robustness results.",
    ),
    (
        "Thank you for asking us to define this composite metric. We will define joint success as simultaneous satisfaction of the request-field, evidence, approval, and execution-status requirements specified before evaluation. We will report separate accept, reject, and clarify confusion matrices for every service and request set, together with the component metrics that form joint success. This presentation will make the safety and completion trade-off visible without relying on one composite rate.",
        "Sections 3 and 5: metric definition and outcome confusion matrices.",
    ),
    (
        "We agree that an analyst benchmark would provide a useful reference point. We will add a human-expert protocol in which qualified analysts prepare the same structured study plan from the same request set, with the displayed information, time, and decision criteria recorded in advance. The comparison will report field accuracy, clarification decisions, completion time, and downstream execution errors. If a fully independent expert sample cannot be completed within the revision period, the manuscript will state that boundary clearly and will avoid claiming analyst-level improvement.",
        "Sections 3, 5, and 7: human-expert benchmark protocol and its scope.",
    ),
    (
        "We appreciate this attribution point and agree with it. The unresolved-default improvement will be described as the effect of a deterministic validation rule within the architecture. The language-model component supplies a candidate structured request; the fixed checker identifies unresolved values and blocks execution until the request is clarified. We will revise the abstract, results, and conclusion so that this result is not attributed to improved language-model capability.",
        "Abstract, Sections 4–7, and Conclusion: attribution of the unresolved-default result.",
    ),
    (
        "Thank you for highlighting the operational burden. We will quantify the 41 clarification cases by number of clarification turns, fields requested, analyst response time, re-evaluation time, final disposition, and unresolved fraction. We will report safety and completion as paired outcomes, so the reader can see the cost of conservative clarification alongside the reduction in rule-violating execution.",
        "Sections 4–6 and Supplementary Material: clarification workload and safety–completion analysis.",
    ),
    (
        "We agree that the two methodological components should be connected with a precise causal boundary. The request-validation layer controls whether a numerical study plan is admissible and whether its information boundary is respected. The reserve-calibration layer determines reserve quantities, coverage, and cost after an admissible plan is accepted. The revised manuscript will trace this hand-off and will avoid attributing the lower reserve cost to the language-model layer.",
        "Sections 1, 3, 5, 6, and 8: contribution boundary and request-to-calculation hand-off.",
    ),
    (
        "We appreciate this suggestion. We will broaden the demand-uncertainty discussion with verified forecasting and planning studies in which demand predictions change renewable-energy decisions. The new discussion will use these studies to clarify why variables available at prediction or decision time must remain separate from later realized outcomes. The added literature will support the information-boundary argument without extending the empirical scope of the present reserve study.",
        "Section 2: demand uncertainty, forecasting, and planning context.",
    ),
    (
        "We agree with this statistical qualification. The revised manuscript will call the reported result empirical rolling-window coverage under the stated temporal split, calibration length, state-selection rule, and screening procedure. It will explicitly separate that empirical quantity from a formal finite-sample conformal guarantee, which is not established for this dependent and adaptively selected setting. Dependence diagnostics and sensitivity analyses will be reported with the calibration results.",
        "Sections 3, 5–7, and Supplementary Material: empirical coverage definition and dependence analysis.",
    ),
    (
        "Thank you for pointing out the unequal reliability constraint. We agree that the cost comparison must use a common service requirement. We will recalibrate or screen the competing policies at the same empirical coverage target, including the 0.95 operational requirement when supported by the data, and will present unequal-coverage comparisons only as secondary diagnostics with explicit qualification. Mean cost and conditional value at risk will be compared after common-constraint screening.",
        "Sections 5–6 and Supplementary Material: common-coverage policy comparison.",
    ),
    (
        "We accept this wording correction. The residual-state scrambling experiment will be described as a sensitivity or counterfactual diagnostic of state selection. We will remove causal language and will state the assumptions that would be needed for a causal interpretation. The result will be used to show dependence on the selected residual state under the fixed prediction, with the inference limited to that controlled comparison.",
        "Sections 5–7 and Conclusion: revised interpretation of residual-state scrambling.",
    ),
    (
        "We agree that anonymized units require a more careful cost description. We will state the normalization formula, identify the unit of the reported normalized cost, and emphasize relative differences when an absolute operational interpretation is unavailable. Any physically interpretable conversion will be reported only where the data and price definitions support it. The manuscript will avoid market claims that cannot be verified from the available information.",
        "Sections 3, 5, and 7 and Supplementary Material: normalized cost definition and interpretation.",
    ),
    (
        "Thank you for this request. We will report calibration and prediction performance separately by season and by extreme-ramp regime, using pre-specified regime definitions and sample counts. The discussion will identify any regime-specific undercoverage or cost change, and aggregate coverage will be presented together with these conditional results. This will keep the operational interpretation focused on periods in which upward reserve is most consequential.",
        "Sections 5–7 and Supplementary Material: seasonal and extreme-ramp analysis.",
    ),
    (
        "We agree that the approval gate requires an operational description. We will specify the approval role, the information displayed before approval, the fields that can be changed, and the audit record produced by the decision. The revised methods will distinguish approval steps that were executed in the experiments from steps represented as a deployment procedure. Any simulated approval will be labelled as such.",
        "Sections 3 and 7: human-approval workflow and experimental status.",
    ),
    (
        "We appreciate this guidance on the conclusion. We will keep the conclusion within the evidence supported by the validated large-language-model-assisted energy-study setting: request interpretation, decision-time information checks, deterministic numerical execution, and empirically evaluated reserve calibration. We will avoid extending the conclusion to arbitrary engineering calculations without a corresponding validation study.",
        "Section 8: narrowed conclusion and scope statement.",
    ),
]


R1_RESPONSE_ZH = [
    (
        "感谢您指出这一边界条件。我们同意，论文贡献需要同时与可复现的非语言模型接口和语言模型输出进行比较。我们将增加受控比较，纳入预定义电子表单、带约束生成的 JavaScript 对象表示法（JavaScript Object Notation，JSON）模式、函数调用接口、有限状态工作流以及更强的确定性解析器。所有方案使用相同的请求字段、可接受性规则和测试案例。我们将报告请求准确率、澄清率、执行错误率、延迟、计算与服务成本以及维护工作量。修订稿将区分结构化请求解释的作用与确定性验证层的作用。",
        "第2–5节及补充材料：替代接口、解析器规范、评估协议和匹配比较表。",
    ),
    (
        "感谢您提醒我们明确规划目标。我们同意，备用策略应先满足既定可靠性要求，再解释成本。我们将把经验覆盖率阈值设为明确的可行性条件，在共同阈值下报告可接受策略，并在筛选完成后比较平均成本和条件风险价值。稿件将说明，更高的采购成本可能直接来自可靠性要求的执行。该修改也会进一步明确备用校准模块在端到端研究中的作用。",
        "第3–6节及补充材料：覆盖率约束、策略筛选、成本比较和敏感性分析。",
    ),
]


R2_RESPONSE_ZH = [
    (
        "感谢您要求加强比较。我们同意，确定性验证可以通过多种结构化接口实现。我们将在相同字段要求和验证规则下，将本文流程与预定义表单、模式约束生成、函数调用接口、有限状态工作流以及更强的确定性解析器进行比较。比较将报告准确率、澄清率、执行错误率、延迟、服务与计算成本以及维护工作量。稿件将把词匹配解析器说明为基线组件，并明确哪些安全效果来自固定验证层。",
        "第2–5节及补充材料：替代接口和匹配评估结果。",
    ),
    (
        "感谢您关注基准独立性。我们同意，基准构建过程需要与规则设计分开记录。我们将报告标注人员数量、专业背景、标注说明、独立双重标注、一致性统计、分歧处理、类别分布以及各请求集的生成过程。我们将增加独立标注的评估集，覆盖释义改写、拼写错误、多语言歧义、提示注入尝试和多轮修正。部署表述将限定在经验证评估数据所覆盖的请求类型内。",
        "第3节、第5节及补充材料：基准构建、标注协议、一致性分析和独立评估集。",
    ),
    (
        "我们同意，每个请求只执行一次不足以刻画随机服务行为。我们将按照有记录的解码设置重复每项服务—请求评估，并归档模型标识符、应用程序接口版本、系统提示、日期、温度、采样参数、token 数量、延迟和服务成本。我们将报告均值、置信区间、失败一致性、成对比较和经多重比较校正的显著性结果。可复现性材料将保留这些记录，使服务更新后的比较结果仍然可以审计。",
        "第3节和第5节、第7节及补充材料：重复运行协议、不确定性估计、元数据归档和成本核算。",
    ),
    (
        "感谢您区分关键词拦截与语义解析。我们同意，未解析默认值检查应被解释为确定性安全门。我们将报告错误澄清率和漏检歧义率，加入不含触发词的隐含歧义案例，并评估完整的澄清闭环，将回答纳入请求后再次检查。当前仍未解析的14个合格请求将进行单独失败分析，记录缺失字段、澄清轮次、最终处置和未完成原因。",
        "第4–6节及补充材料：歧义分类、多轮澄清实验和未解析案例分析。",
    ),
    (
        "我们采纳这一建议。讨论部分将围绕三个相互关联的发现重新组织：信息边界执行、澄清与完成之间的运行权衡，以及既定可靠性要求下的备用校准。每项解释都将对应具体实验，确定性验证结果与数值备用结果分别呈现。修订后的讨论将说明哪些观察属于经验结果，哪些内容属于方法学启示。",
        "第7节：重新组织后的讨论结构和主要发现解释。",
    ),
    (
        "感谢您要求加强方法学背景。我们将补充近期且可核查的优化辅助能源预测、非线性不确定性建模以及智能决策与控制系统研究。新增讨论将把非线性时间序列表征、优化引导预测、面向不确定性的决策支持和变化运行条件下的鲁棒控制，与本文研究的信息边界问题联系起来。所有新增文献都会核对书目信息和与所支持论断的相关性。",
        "第2节：扩展相关工作和核查后的参考文献。",
    ),
    (
        "我们同意，请求验证与备用性能之间需要建立直接追踪关系。我们将构造请求扰动矩阵，分别以及组合改变区域、时间范围、可用变量、成本比、可靠性目标和报告要求。每个被接受的计划都将关联到它改变的确切计算输入和输出。我们将量化错误、不完整、经澄清和正确接受的计划所带来的运行后果。修订稿将明确，备用成本和覆盖率由数值校准方法产生，验证层负责判断所请求计算是否可接受且信息是否充分。",
        "第3–6节及补充材料：请求到计算的可追踪性和端到端扰动分析。",
    ),
    (
        "感谢您提出统计解释方面的澄清。我们同意，当前设置中的目标重叠、共享滚动历史、自适应状态选择和覆盖率筛选不足以支持正式的有限样本保形保证。我们将把报告值表述为经验滚动窗口覆盖率，分析时间依赖性，并报告校准长度、邻域大小、有效样本量、收缩选择和覆盖率筛选阈值的敏感性。在可行情况下，我们将增加分块校准或序贯校准分析。结论将避免把经验值表述为理论保证。",
        "第3节、第5–7节及补充材料：考虑依赖性的校准、敏感性分析和论断边界。",
    ),
    (
        "我们同意，可复现性和外部有效性需要更清晰的数据说明。我们将加入完全公开的高分辨率验证数据集、精确的预处理与缺失数据规则、空间上适配的气象输入，并在公开数据允许时提供具有物理解释的归一化量。对于匿名化主数据集，我们将说明允许公开的聚合信息；涉及货币或市场表现的论断将限定为归一化研究成本，除非能够直接取得备用价格和不平衡惩罚。外部有效性讨论将区分公开验证设置与主区域分析。",
        "第3节、第5节、第7节、数据与代码可用性声明及补充材料：公开验证数据和预处理记录。",
    ),
    (
        "我们采纳这一建议。所有备用策略都将在比较成本和条件风险价值之前，先依据共同的经验覆盖率要求进行筛选。我们将记录预测器结构、超参数选择、场景构造、不确定性集合和计算预算。资源分配示例将标明其示范性质，并说明省略的网络和市场约束及其适用范围。我们也将简化图形，使正常阅读尺寸下仍能清楚看到决策边界和请求到计算的连接。",
        "第3–7节及补充材料：共同约束比较、计算细节、适用范围和修订图形。",
    ),
]


R3_RESPONSE_ZH = [
    (
        "感谢您认真核对研究边界。我们同意，200条请求的盲测试集是在验证规则冻结后生成的合成数据。我们将明确说明这一点，并在可行范围内增加独立编写或独立标注的测试集，同时把部署表述限定在已经验证的请求类别内。稿件将区分规则冻结后的合成评估与运行请求性能证据。",
        "第3、5、7节：盲测试集来源、独立评估和部署边界。",
    ),
    (
        "感谢您提出可复现性要求。我们将长期归档 DeepSeek、通义千问、文心一言和混元服务的标识符、请求日期、解码参数、系统提示、应用程序接口版本和响应记录。归档内容将与请求级评估表关联，并记录修订实验期间遇到的服务变化。",
        "第3节、第7节及可复现性材料：服务元数据和版本记录。",
    ),
    (
        "我们同意，需要重复执行来刻画随机性。我们将针对每项服务和每个请求进行多次独立重复，保留全部响应，并报告联合成功、接受、拒绝和澄清结果的分布及不确定性区间。单次响应结果将不再作为稳健性评估呈现。",
        "第3节、第5节及补充材料：重复运行设计和稳健性结果。",
    ),
    (
        "感谢您要求定义这一复合指标。我们将把联合成功定义为同时满足评估前预先规定的请求字段、证据、审批和执行状态要求。我们将针对每项服务和请求集分别报告接受、拒绝和澄清的混淆矩阵，并列出构成联合成功的分项指标。这样的呈现能够显示安全性与完成度之间的权衡，避免只依赖单一复合率。",
        "第3节和第5节：指标定义和结果混淆矩阵。",
    ),
    (
        "我们同意，分析人员基准能够提供有用的参照。我们将增加人工专家协议，由具备相应资格的分析人员根据相同请求集制定结构化研究计划，并预先记录其可见信息、用时和决策标准。比较将报告字段准确率、澄清决策、完成时间和后续执行错误。若修订期限内无法完成完全独立的专家样本，稿件将清楚说明这一范围，并避免提出达到分析人员水平的改进主张。",
        "第3、5、7节：人工专家基准协议及其适用范围。",
    ),
    (
        "感谢您指出结果归因问题，我们同意这一点。未解析默认值结果的改善将表述为架构内确定性验证规则的作用。语言模型组件提供候选结构化请求，固定检查器识别未解析值，并在请求完成澄清前阻止执行。我们将修改摘要、结果和结论，避免把这一结果归因于语言模型能力提升。",
        "摘要、第4–7节及结论：未解析默认值结果的归因。",
    ),
    (
        "感谢您强调运行负担。我们将按澄清轮次数、所请求字段、分析人员响应时间、重新评估时间、最终处置和未解析比例量化41个澄清案例。我们将把安全性和完成度作为成对结果报告，使读者能够看到保守澄清带来的工作量与规则违规执行减少之间的关系。",
        "第4–6节及补充材料：澄清工作量和安全性—完成度分析。",
    ),
    (
        "我们同意，两个方法学组件需要通过清晰的因果边界连接。请求验证层控制数值研究计划是否可接受，以及其信息边界是否得到遵守。备用校准层在接受合格计划后确定备用数量、覆盖率和成本。修订稿将追踪这一交接过程，并避免把较低备用成本归因于语言模型层。",
        "第1、3、5、6和8节：贡献边界及请求到计算的交接。",
    ),
    (
        "感谢您的建议。我们将通过已核查的预测与规划研究扩展需求不确定性讨论，说明需求预测如何改变可再生能源决策。新增讨论将用于解释，预测时或决策时可获得的变量需要与之后实现的结果分开处理。新增文献将支持信息边界论述，并保持当前备用研究的经验范围。",
        "第2节：需求不确定性、预测和规划背景。",
    ),
    (
        "我们同意这一统计限定。修订稿将把报告结果称为既定时间划分、校准长度、状态选择规则和筛选流程下的经验滚动窗口覆盖率。稿件将明确区分该经验量与正式有限样本保形保证；在当前存在依赖且采用自适应选择的设置下，后者尚未得到建立。校准结果将同时报告依赖性诊断和敏感性分析。",
        "第3节、第5–7节及补充材料：经验覆盖率定义和依赖性分析。",
    ),
    (
        "感谢您指出可靠性约束不一致的问题。我们同意，成本比较需要采用共同服务要求。我们将把竞争策略重新校准或筛选到相同的经验覆盖率目标，并在数据支持时纳入0.95的运行要求；不同覆盖率的比较仅作为经过明确限定的次级诊断。平均成本和条件风险价值将在共同约束筛选后比较。",
        "第5–6节及补充材料：共同覆盖率下的策略比较。",
    ),
    (
        "我们接受这一措辞修正。残差状态置乱实验将被描述为状态选择的敏感性或反事实诊断。我们将删除因果措辞，并说明进行因果解释所需的假设。该结果用于展示在预测固定时对所选残差状态的依赖，推断范围限定在这一受控比较内。",
        "第5–7节及结论：残差状态置乱的修订解释。",
    ),
    (
        "我们同意，匿名化单位需要更谨慎的成本说明。我们将给出归一化公式，明确报告归一化成本的单位，并在缺少绝对运行解释时强调相对差异。只有在数据和价格定义能够支持的情况下，才报告具有物理解释的换算。稿件将避免提出无法由现有信息核查的市场论断。",
        "第3、5、7节及补充材料：归一化成本定义和解释。",
    ),
    (
        "感谢您提出这一要求。我们将按季节和极端爬坡状态分别报告校准与预测性能，使用预先规定的状态定义和样本数量。讨论将指出特定状态下可能出现的覆盖不足或成本变化，并将总体覆盖率与这些条件结果一并呈现。这样可以把运行解释集中在向上备用最重要的时段。",
        "第5–7节及补充材料：季节和极端爬坡分析。",
    ),
    (
        "我们同意，审批门需要运行层面的说明。我们将明确审批角色、审批前显示的信息、可修改字段以及该决策产生的审计记录。修订后的方法将区分实验中实际执行的审批步骤与作为部署流程呈现的步骤。任何模拟审批都会明确标注。",
        "第3节和第7节：人工审批工作流和实验状态。",
    ),
    (
        "感谢您对结论提出指导。我们将把结论限定在经过验证的大语言模型辅助能源研究设置所支持的证据范围内，包括请求解释、决策时信息检查、确定性数值执行和经验评估的备用校准。对于缺少相应验证研究的任意工程计算，我们将不延伸结论。",
        "第8节：收窄后的结论和范围声明。",
    ),
]


R1_RESPONSE_EN = [
    (
        "Thank you for identifying this boundary condition. We agree that structured interfaces and language-model outputs should be compared under the same reproducible request and validation rules. In this revision, we separated the natural-language, structured-record, fixed-validation, and numerical layers, and recorded a matched interface-comparison protocol in the data and supplementary materials. Because this revision does not call external services or implement new independent interfaces, we do not present that comparison as a completed result. The manuscript now attributes the observed safety effect to the fixed validation layer where the archived evidence supports that attribution.",
        "Sections 2–5 and Supplementary Material: layer definitions, comparison protocol, and claim boundary.",
    ),
    (
        "We appreciate this important reminder about the planning objective. We have made the empirical coverage threshold an explicit feasibility condition. The primary comparison now screens policies at the stated level before interpreting cost: the coverage-screened configuration reaches coverage 0.953 with mean normalized cost 1878.05, while the 0.938 configuration and the robust configuration with coverage 0.937 are retained as below-threshold diagnostics. The revised text explains that cost is interpreted together with the reliability requirement and keeps the reserve-calibration result separate from the request-validation result.",
        "Sections 3–6 and Supplementary Material: coverage constraint, policy screening, cost comparison, and sensitivity analysis.",
    ),
]


R2_RESPONSE_EN = [
    (
        "We thank you for this detailed assessment of the manuscript. We have used the numbered points to separate the request-validation study from the reserve-calibration study, strengthen the evidence boundary, and narrow claims to the completed experiments. Several requested comparisons require external service calls, independent annotation, or human participants; their protocols are recorded, while those results are excluded from the present claims.",
        "Opening response to the overall assessment; detailed changes are recorded in the numbered replies below.",
    ),
    (
        "Thank you for requesting a stronger comparison. We agree that deterministic validation can be implemented through several structured interfaces. The revision separates the contribution of structured request interpretation from the contribution of the fixed validation layer and records a matched protocol for a predefined form, schema-constrained generation, a function-calling interface, a finite-state workflow, and a stronger deterministic parser. These new interface implementations were not executed in the current revision, so the manuscript makes no superiority claim for them and reports only the archived framework results.",
        "Sections 2–5 and Supplementary Material: alternative-interface protocol, layer attribution, and evidence boundary.",
    ),
    (
        "We appreciate this concern about benchmark independence. We have documented the provenance of the designed, blind, and controlled request sets, the rule-freezing point, the label definitions, and the distinction between synthetic evaluation and operational evidence. An independently annotated external set was not completed in this revision. The deployment wording is therefore limited to the saved request classes, labels, archived responses, fixed rules, and scoring procedure used in the reported analysis.",
        "Section 3, Section 5, Section 7, and Supplementary Material: benchmark provenance, annotation protocol, and deployment boundary.",
    ),
    (
        "We agree that one archived response per request does not characterize stochastic service behavior. The revision records the required service metadata fields and states that the current service comparison evaluates archived single responses under the recorded settings. No repeated external calls, uncertainty intervals, service-level significance tests, or update-robustness claims are presented. This limitation is now explicit in the methods and scope statements.",
        "Sections 3 and 5, Section 7, and Supplementary Material: metadata schema, single-response evidence, and scope condition.",
    ),
    (
        "Thank you for distinguishing keyword blocking from semantic resolution. We have described the unresolved-default check as a deterministic safety gate and now report its paired effect: it returns 41 clarification-labelled requests for clarification, reduces the observed rule-violating execution rate from 0.205 to 0.000, and leaves the completed-result count at 48 of 62 eligible requests. The 14 eligible requests without a completed result are identified as unresolved cases. A human clarification-turn experiment was not executed, so the manuscript does not claim a measured response-time or resolution-rate benefit.",
        "Sections 4–6 and Supplementary Material: ambiguity handling, paired comparison, and unresolved-case accounting.",
    ),
    (
        "We accept this recommendation. The Discussion is organized around information-boundary enforcement, the clarification--completion trade-off, and reserve calibration under a stated empirical reliability requirement. Each interpretation is tied to its corresponding experiment. The revised text separates empirical observations from methodological implications and keeps the deterministic validation result distinct from the numerical reserve result.",
        "Section 7: revised Discussion structure and interpretation of the main findings.",
    ),
    (
        "We appreciate the request to strengthen the methodological context. We added verifiable literature on optimization-assisted energy forecasting, nonlinear uncertainty modeling, and intelligent decision and control systems. The revised discussion connects nonlinear time-series representation, optimization-guided forecasting, uncertainty-sensitive decision support, and changing operating conditions to the information-boundary problem studied here. The added references were checked for bibliographic accuracy and claim relevance.",
        "Section 2: expanded related work and verified references.",
    ),
    (
        "We agree that the link between request validation and reserve performance needs a precise trace. The revised manuscript attaches request fields to the structured plan, admissibility decision, numerical inputs, calculated outputs, and reported evidence. In the archived paired analysis, both policies produce results for 48 of 62 eligible requests, while the unresolved-default check blocks the 41 rule-violating clarification cases. A broader perturbation matrix and operational-cost study were recorded as protocols; they are not presented as completed evidence in this revision. The reserve quantities and costs remain attributed to the numerical calibration layer.",
        "Sections 3–6 and Supplementary Material: request-to-calculation traceability and completed paired analysis.",
    ),
    (
        "Thank you for the statistical clarification. We agree that overlapping targets, shared rolling histories, adaptive state selection, and coverage screening do not support a formal finite-sample conformal guarantee in the present setting. The revised manuscript calls 0.953 empirical rolling-window coverage under the stated splits and screening procedure. It discusses temporal dependence, calibration and state-selection choices, and sensitivity results, and it avoids presenting the empirical value as a theoretical guarantee.",
        "Sections 3, 5–7, and Supplementary Material: empirical coverage definition, dependence discussion, sensitivity analysis, and claim boundary.",
    ),
    (
        "We agree that reproducibility and external validity require clearer data documentation. The revision specifies the preprocessing rules, missing-data handling, weather sources, normalized study-cost interpretation, and the harmonized five-region validation panel. That panel is described as cross-region validation within the available data, not as a full independent replication of the anonymized primary dataset. Claims about monetary or market performance are excluded when the available information cannot support them.",
        "Sections 3, 5, and 7, Data and code availability statement, and Supplementary Material: data provenance, preprocessing, normalized cost, and external-validity boundary.",
    ),
    (
        "We accept this recommendation. The policy comparison now applies the common empirical coverage screen before the primary cost interpretation. The coverage-screened configuration reaches 0.953 coverage at mean normalized cost 1878.05. The 0.938 configuration and the robust configuration at 0.937 are reported as below-threshold diagnostics, with robust mean normalized cost 1965.58. Predictor structure, rolling design, scenario construction, resource-accounting assumptions, and omitted system constraints are documented, and the figures were simplified to keep the decision boundary and request-to-calculation path visible.",
        "Sections 3–7 and Supplementary Material: common-constraint comparison, computational details, scope conditions, and revised figures.",
    ),
]


R3_RESPONSE_EN = [
    (
        "We thank you for the careful reading of the study boundary. We agree that the 200-request blind set is synthetic because it was generated after the validation rules were frozen. The revision states this provenance explicitly and restricts deployment language to the saved request classes and evaluation procedure. Independent operational-request evidence was not collected in this revision, so no broader deployment claim is made.",
        "Sections 3, 5, and 7: blind-set provenance, evaluation boundary, and deployment wording.",
    ),
    (
        "We appreciate this reproducibility requirement. The revision records the requested model identifiers, returned identifiers where available in the archive, generation settings, system-prompt field, request dates, and application programming interface metadata fields. The package also records which values belong to the saved archive. No new service call was made during this revision, so the archive is presented as a record of the reported single-response experiment and not as a guarantee against later service changes.",
        "Section 3, Section 7, and the reproducibility package: service metadata and version records.",
    ),
    (
        "We agree that repeated execution is needed to characterize stochasticity. The current revision retains the archived single-response analysis and records a repeated-run schema and protocol. Multiple new service repetitions, response distributions, and uncertainty intervals were not obtained, so the manuscript does not describe the single-response results as robustness estimates.",
        "Sections 3 and 5 and Supplementary Material: repeated-run protocol and evidence limitation.",
    ),
    (
        "Thank you for asking us to define this composite metric. We have defined joint success as simultaneous satisfaction of the applicable request-field, evidence, approval, result-source, parsing, and execution-status checks. The supplementary material reports the component metrics and outcome-specific counts for the archived request sets. Repeated-run confusion matrices are outside the current evidence because the required external repetitions were not performed.",
        "Sections 3 and 5 and Supplementary Material: joint-success definition and component outcomes.",
    ),
    (
        "We agree that an analyst benchmark would provide a useful reference point. The revision records a human-expert benchmark protocol with the required visibility, timing, decision criteria, and downstream-error fields. No independent analyst sample was completed, so the manuscript makes no claim of analyst-level performance or time reduction.",
        "Sections 3, 5, and 7: human-expert benchmark protocol and scope.",
    ),
    (
        "We appreciate this attribution point and agree with it. The unresolved-default improvement is now described as the effect of a deterministic validation rule within the architecture. The language-model component supplies candidate structured fields; the fixed checker identifies unresolved values and blocks execution until the request is sufficiently specified. The abstract, results, Discussion, and conclusion now assign this safety effect to the validation architecture.",
        "Abstract, Sections 4–7, and Conclusion: attribution of the unresolved-default result.",
    ),
    (
        "Thank you for highlighting the operational burden. The revision makes the 41 clarification cases, the 14 eligible unresolved cases, and the 48 completed results among 62 eligible requests explicit. The available archive does not contain human response-time or multi-turn completion measurements, so the manuscript reports the safety--completion trade-off without inventing a clarification-time estimate.",
        "Sections 4–6 and Supplementary Material: clarification workload and safety--completion analysis.",
    ),
    (
        "We agree that the two methodological components should be connected with a precise boundary. The request-validation layer determines whether a study plan is admissible and respects the decision-time information boundary. The reserve-calibration layer determines reserve quantities, coverage, and cost after an admissible plan is accepted. The revised manuscript traces this hand-off and does not attribute reserve-cost differences to the language-model component.",
        "Sections 1, 3, 5, 6, and 8: contribution boundary and request-to-calculation hand-off.",
    ),
    (
        "We appreciate this suggestion. We added verified forecasting and planning studies that connect demand uncertainty with renewable-energy decisions, uncertainty-sensitive planning, and changing operating conditions. The discussion uses this literature to clarify the separation between decision-time variables and later realized outcomes. It does not extend the empirical scope of the reserve study.",
        "Section 2: demand uncertainty, forecasting, and planning context.",
    ),
    (
        "We agree with this statistical qualification. The revised manuscript calls the reported value empirical rolling-window coverage under the stated temporal split, calibration length, state-selection rule, and screening procedure. It separates this empirical quantity from a formal finite-sample conformal guarantee, which is not established for the dependent and adaptively selected setting. Dependence considerations and sensitivity analyses are reported with the calibration results.",
        "Sections 3, 5–7, and Supplementary Material: empirical coverage definition and dependence analysis.",
    ),
    (
        "Thank you for pointing out the unequal reliability constraint. The revision applies a common empirical coverage screen before the primary cost comparison. The coverage-screened configuration reaches 0.953 coverage at mean normalized cost 1878.05. The 0.938 and 0.937 configurations remain explicitly labelled below-threshold diagnostics, with the robust configuration at mean normalized cost 1965.58. Unequal-coverage results are not used as the primary like-for-like comparison.",
        "Sections 5–6 and Supplementary Material: common-coverage policy comparison.",
    ),
    (
        "We accept this wording correction. The residual-state scrambling experiment is described as a controlled sensitivity diagnostic for state selection. The revised text removes causal language and keeps the inference within the fixed-prediction comparison: scrambling raises mean cost by 175.58 while the base prediction and evaluation design remain fixed.",
        "Sections 5–7 and Conclusion: revised interpretation of residual-state scrambling.",
    ),
    (
        "We agree that anonymized units require a careful cost description. The revision gives the normalized study-cost definition, identifies the interpretation supported by the available data, and emphasizes relative differences when an absolute operational conversion cannot be verified. Market claims that require unavailable reserve prices or imbalance penalties have been removed.",
        "Sections 3, 5, and 7 and Supplementary Material: normalized cost definition and interpretation.",
    ),
    (
        "Thank you for this request. The revision reports seasonal and operating-regime diagnostics with pre-specified definitions and sample counts. The discussion places the aggregate empirical coverage beside the seasonal and difficult-regime results and keeps below-threshold conditional values as diagnostics. The operational interpretation is therefore focused on the periods represented in the evaluated reserve study.",
        "Sections 5–7 and Supplementary Material: seasonal and operating-regime analysis.",
    ),
    (
        "We agree that the approval gate requires an operational description. The revision specifies the approval role, information displayed before approval, editable fields, status transition, and audit record. It also labels the approval field in the reported experiment as a simulated Boolean workflow gate and separates that experiment record from a future live-operator workflow.",
        "Sections 3 and 7: human-approval workflow and experimental status.",
    ),
    (
        "We appreciate this guidance on the conclusion. The conclusion is limited to the evidence supported by the evaluated large-language-model-assisted energy-study setting: request interpretation, decision-time information checks, deterministic numerical execution, and empirical reserve calibration. It does not extend to arbitrary engineering calculations without a corresponding validation study.",
        "Section 8: narrowed conclusion and scope statement.",
    ),
]


R1_RESPONSE_ZH = [
    (
        "感谢您指出这一边界条件。我们同意，应将结构化接口和大语言模型输出放在相同的请求字段与校验规则下进行可复现比较。本次修订已分开定义自然语言层、结构化记录层、固定校验层和数值计算层，并在数据协议和补充材料中记录接口对照方案。由于本轮没有调用外部服务，也没有实现新的独立接口，稿件没有把该比较写成已完成结果。现有安全性结果已按照证据归因于固定校验层，相关表述已经收窄。",
        "第2–5节及补充材料：层次定义、接口比较协议和论断边界。",
    ),
    (
        "感谢您提醒我们明确规划目标。我们已把经验覆盖率阈值设为可行性条件，并在解释成本前先按共同要求筛选策略。覆盖率筛选配置达到 0.953，平均归一化成本为 1878.05；覆盖率为 0.938 的配置和覆盖率为 0.937 的稳健配置保留为低于阈值的诊断结果。修订稿把成本与可靠性要求结合解释，并清楚区分请求验证结果与备用校准结果。",
        "第3–6节及补充材料：覆盖率约束、策略筛选、成本比较和敏感性分析。",
    ),
]


R2_RESPONSE_ZH = [
    (
        "感谢您对稿件作出的细致评价。我们已按照编号意见区分请求验证研究与备用校准研究，明确证据边界，并收窄结论范围。部分建议需要外部服务调用、独立标注或人工参与；相应协议已经记录，当前稿件没有把尚未取得的结果写入论断。",
        "总体意见的承接说明；具体修改见以下逐条回复。",
    ),
    (
        "感谢您要求加强比较。我们同意，确定性验证可以通过多种结构化接口实现。修订稿分开说明结构化请求解释和固定校验层的作用，并在数据与补充材料中记录预定义电子表单、约束模式生成、函数调用接口、有限状态流程和增强型确定性解析器的匹配比较协议。本轮没有实现这些新的接口，因此稿件没有提出它们的优越性结论，现有结果仅对应已归档的框架实验。",
        "第2–5节及补充材料：替代接口协议、层次归因和证据边界。",
    ),
    (
        "感谢您指出基准独立性问题。我们已补充设计集、盲测集和受控请求集的来源、规则冻结时间、标签定义，以及合成评估与运行证据之间的区别。本次修订没有完成独立外部标注集，因此部署表述限定在已保存的请求类别、标签、归档响应、固定规则和评分流程内。",
        "第3节、第5节、第7节及补充材料：基准来源、标注协议和部署边界。",
    ),
    (
        "我们同意，每个请求只保留一次响应无法刻画服务随机性。修订稿记录了服务元数据所需字段，并明确当前服务比较使用在既定设置下保存的单次响应。稿件没有报告重复外部调用、重复运行置信区间、服务间显著性检验或对服务更新的稳健性结论。该限制已写入方法和范围说明。",
        "第3节和第5节、第7节及补充材料：元数据结构、单次响应证据和范围条件。",
    ),
    (
        "感谢您区分关键词阻断与语义消歧。我们已将未解决默认值检查描述为确定性安全门，并报告其配对效果：41 个标记为需要澄清的请求被退回澄清，观察到的规则违规执行率由 0.205 降至 0.000，62 个合格请求中仍有 48 个产生完成结果。其余 14 个合格请求列为未解决案例。当前没有执行人工多轮澄清实验，因此稿件没有宣称已测得响应时间或解决率收益。",
        "第4–6节及补充材料：歧义处理、配对比较和未解决案例统计。",
    ),
    (
        "我们采纳这一建议。讨论部分围绕信息边界约束、澄清与完成之间的运行权衡，以及给定经验可靠性要求下的备用校准展开。每项解释均与相应实验对应，经验观察与方法学含义分开陈述，确定性验证结果和数值备用结果保持独立。",
        "第7节：讨论结构和主要发现解释。",
    ),
    (
        "感谢您要求加强方法学背景。我们补充了可核查的优化辅助能源预测、非线性不确定性建模以及智能决策与控制系统研究。修订后的讨论把非线性时间序列表征、优化引导预测、面向不确定性的决策支持和变化运行条件与本文的信息边界问题联系起来。新增文献已经核对书目信息和论断关联性。",
        "第2节：扩展后的相关工作和已核查文献。",
    ),
    (
        "我们同意，请求验证与备用性能之间需要精确追踪。修订稿把请求字段连接到结构化计划、可接受性判断、数值输入、计算输出和报告证据。归档配对分析中，62 个合格请求有 48 个在两种策略下产生结果；未解决默认值检查阻止了 41 个违反规则的澄清案例进入计算。更广泛的请求扰动矩阵和运行成本研究已经记录为协议，本次修订没有把它们写成已完成证据。备用数量和成本仍归因于数值校准层。",
        "第3–6节及补充材料：请求到计算的追踪和已完成的配对分析。",
    ),
    (
        "感谢您提出统计解释方面的澄清。我们同意，目标重叠、共享滚动历史、自适应状态选择和覆盖率筛选不足以支持当前设置下的正式有限样本保形保证。修订稿把 0.953 称为给定数据划分和筛选程序下的经验滚动窗口覆盖率，并讨论时间依赖、校准设置、状态选择和敏感性结果。稿件没有把该经验值表述为理论保证。",
        "第3节、第5–7节及补充材料：经验覆盖率定义、依赖性讨论、敏感性分析和论断边界。",
    ),
    (
        "我们同意，可复现性和外部有效性需要更清楚的数据说明。修订稿给出预处理规则、缺失数据处理、天气来源、归一化研究成本的解释，以及协调后的五区域验证面板。该面板被表述为现有数据范围内的跨区域验证，没有写成对匿名主数据集的完整独立复现。现有信息无法支持的货币或市场论断已经删除。",
        "第3、5、7节、数据与代码可用性声明及补充材料：数据来源、预处理、归一化成本和外部有效性边界。",
    ),
    (
        "我们采纳这一建议。策略比较先按共同经验覆盖率要求筛选，再解释主要成本结果。覆盖率筛选配置达到 0.953，平均归一化成本为 1878.05；覆盖率为 0.938 的配置和覆盖率为 0.937 的稳健配置明确列为低于阈值的诊断结果，稳健配置的平均归一化成本为 1965.58。预测器结构、滚动设计、场景构造、资源核算假设和省略的系统约束已经记录，图形也已简化，以突出决策边界和请求到计算的连接。",
        "第3–7节及补充材料：共同约束比较、计算细节、范围条件和修订图形。",
    ),
]


R3_RESPONSE_ZH = [
    (
        "感谢您认真核对研究边界。我们同意，200 条请求的盲测集是在验证规则冻结后生成的合成数据。修订稿明确说明这一来源，并把部署表述限定在已保存的请求类别和评估流程内。本次修订没有取得运行操作员请求的独立证据，因此没有提出更广泛的部署结论。",
        "第3、5、7节：盲测集来源、评估边界和部署表述。",
    ),
    (
        "感谢您提出可复现性要求。修订稿记录了请求模型标识、归档中可获得的返回标识、生成设置、系统提示字段、请求日期和应用程序接口元数据字段，并标明哪些信息属于已保存的归档。本轮没有发起新的服务调用，因此该归档被表述为已报告单次响应实验的记录，没有被写成对后续服务变化的保证。",
        "第3节、第7节及可复现性材料：服务元数据和版本记录。",
    ),
    (
        "我们同意，需要通过重复执行刻画随机性。当前修订保留已归档的单次响应分析，并记录了重复运行的数据结构和协议。本轮没有取得新的服务重复响应、响应分布和不确定性区间，因此稿件没有把单次响应结果称为稳健性估计。",
        "第3、5节及补充材料：重复运行协议和证据限制。",
    ),
    (
        "感谢您要求定义这一复合指标。我们已把联合成功定义为同时满足适用的请求字段、证据、审批、结果来源、解析和执行状态检查。补充材料报告了归档请求集的构成指标和结果类别计数。由于所需的外部重复运行没有执行，重复运行混淆矩阵没有纳入当前证据。",
        "第3、5节及补充材料：联合成功定义和构成结果。",
    ),
    (
        "我们同意，分析人员基准能够提供有用参照。修订稿记录了人工专家基准协议，包括可见信息、计时规则、决策标准和后续错误字段。本次修订没有完成独立分析人员样本，因此稿件没有提出达到分析人员水平或节省时间的结论。",
        "第3、5、7节：人工专家基准协议和适用范围。",
    ),
    (
        "感谢您指出结果归因问题，我们同意这一判断。修订稿把未解决默认值检查的改善描述为架构内确定性校验规则的作用。大语言模型提供候选结构化字段，固定检查器识别未解决值，并在请求信息充分前阻止执行。摘要、结果、讨论和结论已经把该安全效果归因于验证架构。",
        "摘要、第4–7节和结论：未解决默认值结果的归因。",
    ),
    (
        "感谢您指出运行负担。修订稿明确了 41 个澄清案例、14 个未完成的合格案例，以及 62 个合格请求中的 48 个完成结果。现有归档没有人工响应时间和多轮完成测量，因此稿件报告安全性与完成率之间的权衡，没有补写澄清耗时估计。",
        "第4–6节及补充材料：澄清负担和安全性—完成率分析。",
    ),
    (
        "我们同意，两部分方法需要清楚的边界。请求验证层判断研究计划是否可接受，并检查其是否遵守决策时信息边界；备用校准层在计划通过后确定备用数量、覆盖率和成本。修订稿追踪了这一交接过程，没有把备用成本差异归因于大语言模型组件。",
        "第1、3、5、6、8节：贡献边界和请求到计算的交接。",
    ),
    (
        "感谢您的建议。我们补充了把需求不确定性与可再生能源决策、面向不确定性的规划和变化运行条件联系起来的可核查预测与规划研究。讨论借助这些文献说明决策时变量与之后实现的结果之间的区别，没有扩大本文备用研究的实证范围。",
        "第2节：需求不确定性、预测和规划背景。",
    ),
    (
        "我们同意这一统计限定。修订稿把报告值称为给定时间划分、校准长度、状态选择规则和筛选程序下的经验滚动窗口覆盖率，并将其与当前依赖性和自适应选择设置下尚未建立的正式有限样本保形保证分开。校准结果同时报告了依赖性考虑和敏感性分析。",
        "第3节、第5–7节及补充材料：经验覆盖率定义和依赖性分析。",
    ),
    (
        "感谢您指出可靠性约束不一致的问题。修订稿在主要成本比较前采用共同经验覆盖率筛选。覆盖率筛选配置达到 0.953，平均归一化成本为 1878.05；0.938 和 0.937 两个配置保留为低于阈值的诊断结果，稳健配置的平均归一化成本为 1965.58。不同覆盖率下的结果没有作为主要同口径比较。",
        "第5–6节及补充材料：共同覆盖率下的策略比较。",
    ),
    (
        "我们采纳这一措辞修正。残差状态置乱实验被描述为状态选择的受控敏感性诊断。修订稿删除了因果措辞，并把推断限制在固定预测的比较内：在基础预测和评估设计保持不变时，置乱使平均成本增加 175.58。",
        "第5–7节和结论：残差状态置乱的修订解释。",
    ),
    (
        "我们同意，匿名化单位需要谨慎说明成本。修订稿给出归一化研究成本的定义，说明现有数据支持的解释，并在无法核查绝对运行换算时强调相对差异。需要备用价格或不平衡惩罚才能成立的市场论断已经删除。",
        "第3、5、7节及补充材料：归一化成本定义和解释。",
    ),
    (
        "感谢您提出这一要求。修订稿按预先规定的状态定义和样本数量报告季节与运行状态诊断。讨论把总体经验覆盖率与季节和困难状态结果并列呈现，并将低于阈值的条件结果保留为诊断信息。运行解释限定在当前备用研究实际覆盖的时段。",
        "第5–7节及补充材料：季节和运行状态分析。",
    ),
    (
        "我们同意，审批门需要运行层面的说明。修订稿明确审批角色、审批前展示的信息、可修改字段、状态转移和审计记录，并把实验中的审批字段标记为模拟的布尔工作流门。实验记录与未来的真实操作员流程已经分开描述。",
        "第3节和第7节：人工审批工作流和实验状态。",
    ),
    (
        "感谢您对结论提出指导。结论已限定在经过评估的大语言模型辅助能源研究设置所支持的证据范围内，包括请求解释、决策时信息检查、确定性数值执行和经验备用校准。对于缺少相应验证研究的任意工程计算，结论没有延伸。",
        "第8节：收窄后的结论和范围声明。",
    ),
]


R2_COMMENT_TRANSLATION = [
    "验证组件的创新性应与更强的非大语言模型方案和受约束生成方案比较。许多安全收益似乎来自大语言模型生成结构化记录之后执行的确定性检查。预定义电子表单、带约束解码的 JSON 模式、函数调用接口、有限状态流程或传统规则引擎，都可能以更高的可复现性执行相同的区域、时间范围、变量、审批和证据要求。当前的词匹配解析器不足以公平代表这些替代方案。作者应比较所提框架、模式约束生成、结构化表单和更强的确定性解析器，并报告准确率、澄清率、执行错误、延迟、成本和维护工作量。",
    "请求基准的构建和标注需要独立验证。设计集、盲测集和受控请求集似乎由定义检查规则的同一研究团队创建并标注。这可能使基准与框架高度一致，也可能部分解释设计案例上的完美表现。稿件应报告标注人数、专业背景、标注说明、独立双重标注、标注者一致性、分歧处理、类别分布和请求生成过程。需要加入由外部人员编写或独立标注的测试集，包含真实操作员请求、释义、拼写错误、多语言歧义、提示注入和多轮修正，以支持泛化结论。",
    "大语言模型评估对随机性和服务演化的处理不充分。研究似乎为每个请求和服务只评估了一次保存的响应，而托管模型可能在不通知的情况下改变，也可能在重复调用时产生不同输出。仅报告返回的模型标识并不能保证可复现。每个请求都应在记录温度、采样参数、系统提示和日期的条件下执行多次独立运行。应报告平均性能、置信区间、失败一致性、token 使用量、延迟和 API 成本。在解释 0.705–0.885 的联合成功率差异前，还需要进行服务间成对统计比较并校正多重检验。",
    "未解决默认值实验目前主要产生了规则诱导结果。新增检查明确识别“usual”“normal”“standard”和“default”等短语，之后违反规则的计算从 0.205 降为零，因为被标记的请求被阻止继续执行。这证明阻止含糊关键词能够减少执行，却没有证明系统理解并成功解决了歧义。作者应报告错误澄清率和遗漏歧义率，测试不含触发词的隐含歧义，并开展完整的多轮实验，在澄清问题得到回答后重新评估修订请求。只有 62 个合格请求中的 48 个最终产生结果，因此还需要详细分析未解决的 14 个案例。",
    "Discussion 部分应以更突出、更有论证性的方式编辑。作者应分析测试结果得以实现的原因。",
    "文献综述应进一步加强，加入近期关于优化辅助能源预测、非线性不确定性建模以及智能决策与控制系统的研究。尽管这些研究针对不同能源应用，但它们为非线性时间序列表征、优化引导预测、面向不确定性的决策支持以及变化运行条件下的稳健人工智能控制提供了相关方法视角。讨论这些贡献有助于拓宽所提大语言模型辅助验证框架的方法学背景，并加强可靠能源预测、运行决策和智能控制之间的联系。",
    "请求验证与备用性能之间的端到端关系仍然较弱。备用实验使用了基本固定的数值流程，而大多数被接受的请求似乎只是从预定的区域、时间范围、成本比和证据字段中进行选择。因此，备用成本和覆盖率的改善来自校准方法，而非大语言模型验证层。作者应评估一组更广泛的已接受请求，使其真正改变区域、时间范围、可用变量、成本比、可靠性目标和报告要求。随后应将每个请求字段追踪到执行计算中的可验证变化，并量化错误、不完整、被澄清和正确接受的计划所带来的运行成本。",
    "保形校准的论断需要更谨慎的统计处理。四个未来步长上的十五分钟目标彼此重叠，相邻滚动窗口共享大量训练历史，这会破坏简单的独立性或可交换性假设。此外，残差状态和收缩选择使用 10 天选择区块，而覆盖率筛选策略依据经验覆盖率在局部校准和全局校准之间选择。因此之后得到的 0.953 覆盖率是经验结果，并非有保证的 95% 保形覆盖性质。作者应清楚区分经验覆盖率和理论保证，分析时间依赖性，采用适当的区块式或序贯保形程序，报告不同状态下的条件覆盖率，并研究校准长度、邻域大小、有效样本量和选择阈值的敏感性。",
    "能源分析的可复现性和外部有效性仍然有限。核心的 315,302 条观测数据经过匿名化且不可获得，负荷单位未公开，归一化成本无法从经济角度解释。外部验证在一定程度上弥补了这一限制，但一个机场站点很难代表 ERCOT、CAISO 或 MISO 等大型平衡区域的天气暴露。作者应至少在一个完全公开的高分辨率数据集上复现主要发现，提供精确的预处理和缺失数据规则，使用具有空间代表性的天气信息，并以归一化且具有物理解释的单位报告结果。在纳入真实备用价格和不平衡惩罚之前，应降低货币或市场导向的论断。",
    "备用策略比较和实际系统结论需要更强的控制。若干竞争方法未达到所述的 0.95 覆盖率，而所提覆盖率筛选配置明确以达到该阈值为设计目标，因此成本比较并不完全同口径。所有策略都应先校准到共同的经验覆盖率或可靠性约束，再比较成本和 CVaR。还应记录预测器结构、超参数调优、场景构造、不确定集和计算预算。资源分配研究仍属示例，因为它省略了网络约束、机组组合、爬坡限制、市场出清和事故情景。图形应简化并重新设计，突出端到端创新和决策边界，避免依赖密集的模块图和拥挤的多面板图形。",
]


R3_COMMENT_TRANSLATION = [
    "200 条请求的盲测集是在框架规则冻结后由作者设计的。从方法学角度看，这避免了在同一案例上调参，但这些请求仍然是合成的。在声称具有部署有效性之前，需要使用真实操作员或分析员请求进行评估。",
    "评估的四项服务 DeepSeek、Qwen、ERNIE 和 Hunyuan 提供了有价值的服务多样性，但大语言模型服务演化很快。模型标识、日期、解码参数和 API 版本应与复现包永久存档。",
    "由于大语言模型输出具有随机性，理想情况下每个请求都应在每项服务上多次执行。每个请求只响应一次只能测量服务的一次实现，无法衡量稳健性。",
    "稿件应明确定义“联合成功”，并报告接受、拒绝和澄清结果的混淆矩阵，不能主要依赖一个综合比率。",
    "人工专家基准会很有价值。核心问题不仅是确定性检查能否改善大语言模型输出，也包括大语言模型加检查器的流程是否相对于分析员准备同一研究计划减少了错误或时间。",
    "未解决默认值检查带来的改善很重要，但它由确定性验证规则产生，而非由大语言模型本身产生。论文应准确将这一结果归因于验证架构，而非语言模型能力提升。",
    "返回 41 个含糊案例要求澄清在运行上较为保守，但澄清负担也应量化。安全性与完成率之间存在真实权衡。",
    "稿件包含两个相对独立的方法学贡献：请求验证和依赖状态的备用校准。应进一步阐明二者的关系。备用成本下降来自数值校准方法，而非大语言模型层。",
    "需求不确定性讨论可以通过预测与规划研究拓展，在这些研究中需求预测会直接改变可再生能源决策。这些文献能够提供另一个能源系统例子，说明预测或决策时可用的信息必须与之后实现的结果清楚分离。",
    "保形推断通常依赖可交换性假设，而在强自相关的电力时间序列中这一点并不直接成立。作者应清楚区分经验滚动窗口校准与任何形式的有限样本覆盖保证。",
    "报告覆盖率为 0.953 的配置与覆盖率为 0.937 的鲁棒优化进行了比较。如果运行覆盖率要求是 0.95，那么鲁棒比较方法没有满足同一可靠性约束，因此其成本不能在没有限定的情况下被解释为同等服务比较。",
    "残差状态打乱实验证明了对状态选择的敏感性。除非建立因果解释所需的假设，否则不应把它描述为因果证据。",
    "使用匿名负荷单位使绝对平均成本 1878.05 和 1965.58 难以从运行角度解释。应澄清归一化成本公式，或重点报告相对成本差异。",
    "稿件应按季节和极端爬坡区间分别报告校准与预测性能。平均覆盖率可能掩盖备用最重要时段的覆盖不足。",
    "人工审批门在概念上很重要。请说明由谁提供审批、审批者能看到哪些信息，以及实验中的人工审批是模拟的还是实际取得的。",
    "当前稿件对数值来源的处理非常谨慎。结论应保持这一狭窄贡献范围，避免在没有验证的情况下将框架推广到任意大语言模型辅助工程计算。",
]


def set_run_font(run, chinese: bool = False, size: int = 11) -> None:
    run.font.name = "Times New Roman"
    run.font.size = Pt(size)
    fonts = run._element.get_or_add_rPr().get_or_add_rFonts()
    fonts.set(qn("w:ascii"), "Times New Roman")
    fonts.set(qn("w:hAnsi"), "Times New Roman")
    fonts.set(qn("w:eastAsia"), "SimSun" if chinese else "Times New Roman")


def add_page_number(paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.extend((begin, instr, end))
    set_run_font(run)


def paragraph_role(text: str) -> str:
    if not text:
        return "blank"
    if text.startswith(("Comment:", "审稿意见原文：")):
        return "comment"
    if text.startswith(("中文直译：", "Response:", "回复：")):
        return "response" if text.startswith(("Response:", "回复：")) else "translation"
    if text.startswith(("Revised manuscript location:", "稿件位置：")):
        return "location"
    if re.fullmatch(r"R[123]-\d+", text):
        return "item"
    if text.startswith(("Responses to Reviewer", "对审稿人", "Overall assessment", "总体意见")):
        return "heading"
    if text.startswith(("Dear ", "尊敬的")):
        return "salutation"
    if text in {"Sincerely,", "此致", "Yanhong Zhong", "Corresponding Author"} or text.startswith(("Sincerely,\n", "此致\n")):
        return "closing"
    return "body"


def add_label_and_text(paragraph, label: str, text: str, chinese: bool) -> None:
    run = paragraph.add_run(label + " ")
    set_run_font(run, chinese)
    run.bold = True
    run = paragraph.add_run(text)
    set_run_font(run, chinese)


def make_paragraph(doc, text: str, chinese: bool, first: bool = False) -> None:
    role = paragraph_role(text)
    if role == "blank":
        return
    paragraph = doc.add_paragraph()
    fmt = paragraph.paragraph_format
    fmt.line_spacing_rule = WD_LINE_SPACING.SINGLE
    fmt.line_spacing = 1.15
    fmt.space_before = Pt(0)
    fmt.space_after = Pt(6)
    fmt.first_line_indent = Inches(0)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    if first:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        fmt.space_after = Pt(12)
    elif role == "heading":
        paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
        fmt.space_before = Pt(12)
        fmt.keep_with_next = True
    elif role == "item":
        paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
        fmt.left_indent = Inches(0.2)
        fmt.space_before = Pt(10)
        fmt.space_after = Pt(4)
        fmt.keep_with_next = True
    elif role == "comment":
        fmt.left_indent = Inches(0.25)
        fmt.right_indent = Inches(0.08)
        fmt.space_after = Pt(4)
    elif role in {"translation", "response"}:
        fmt.left_indent = Inches(0.4)
        fmt.right_indent = Inches(0.04)
        fmt.space_after = Pt(4)
    elif role == "location":
        fmt.left_indent = Inches(0.4)
        fmt.space_after = Pt(8)
    elif role in {"salutation", "closing"}:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
        fmt.space_after = Pt(2 if role == "closing" else 6)

    prefixes = (
        "Comment:",
        "审稿意见原文：",
        "中文直译：",
        "Response:",
        "回复：",
        "Revised manuscript location:",
        "稿件位置：",
    )
    for prefix in prefixes:
        if text.startswith(prefix):
            add_label_and_text(paragraph, prefix, text[len(prefix):].lstrip(), chinese)
            break
    else:
        run = paragraph.add_run(text)
        set_run_font(run, chinese)

    if first or role in {"heading", "item"}:
        for run in paragraph.runs:
            run.bold = True


def write_text(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(line for line in lines if line) + "\n", encoding="utf-8", newline="\n")


def build_english(r1a: str, r1: list[str], r2overall: str, r2: list[str], r3overall: str, r3: list[str]) -> list[str]:
    lines = [
        "Response to the Editor and Reviewers",
        "Dear Editor-in-Chief, Associate Editor, and Reviewers,",
        "We sincerely thank the editorial team and the reviewers for the opportunity to revise manuscript ADVEI-D-26-08441, entitled \"A decision-time validation framework for LLM-assisted energy studies: One-hour upward-reserve sizing.\" We have read every comment carefully and have organized the revision around information-boundary validation, benchmark independence, stochastic-service reproducibility, and a common reliability constraint for reserve-policy comparison.",
        "The revised package is prepared for the Energy Virtual Special Issue (VSI) of Advanced Engineering Informatics (AEI). The revision keeps the paper within this VSI by linking a human energy-study request, a structured engineering plan, decision-time information, deterministic numerical execution, and reserve decisions under uncertainty. The manuscript states this scope explicitly and separates empirical findings from claims that require formal guarantees.",
        "The completed offline revision actions are as follows.",
        "(1) We specified matched comparison protocols for structured forms, constrained generation, function calling, finite-state processing, and a stronger deterministic parser. These service- or implementation-dependent comparisons remain recorded as protocols; the current results use the available evidence base.",
        "(2) We documented benchmark construction, annotation fields, request-set provenance, and the independent-evaluation design recorded for future data collection.",
        "(3) We archived the available model and application programming interface metadata and labelled the current service evidence as single-response evidence. Repeated hosted-service evaluations, new model or application programming interface calls, and their uncertainty estimates remain outside the current results.",
        "(4) We completed the offline clarification-loop analysis, quantified the workload represented by the 41 ambiguous cases, and traced accepted request fields to numerical calculation inputs.",
        "(5) We distinguished empirical rolling-window coverage from formal conformal guarantees and compared reserve policies after applying a common empirical coverage requirement.",
        "(6) We strengthened the energy-system literature context, public-data validation, seasonal and extreme-ramp analysis, human-approval description, and scope conditions. Real operator approval and new external annotation remain protocol items because they require additional data collection.",
        "The current package therefore contains all offline manuscript, supplement, response-letter, source-package, and compilation changes. External API calls and other live data-collection activities are explicitly separated from the completed evidence.",
        "The marked manuscript uses blue text for additions, red strikethrough for deletions, and blue reviewer labels at material changes. The unmarked manuscript contains the clean revised text. The response below reproduces every reviewer comment in full and gives a specific response and manuscript location for each item.",
        "Responses to Reviewer #1",
        "Thank you for the focused comments on decision-time information boundaries and hard coverage constraints. We agree that both points should be visible in the method definition and in the reserve-policy comparison.",
        "R1-1",
        f"Comment: {r1[0]}",
        f"Response: {R1_RESPONSE_EN[0][0]}",
        f"Revised manuscript location: {R1_RESPONSE_EN[0][1]}",
        "R1-2",
        f"Comment: {r1[1]}",
        f"Response: {R1_RESPONSE_EN[1][0]}",
        f"Revised manuscript location: {R1_RESPONSE_EN[1][1]}",
        "Thank you again for the precise guidance on the information boundary and the reliability requirement.",
        "Responses to Reviewer #2",
        "Overall assessment",
        f"Comment: {r2overall}",
        f"Response: We thank you for this balanced assessment and for identifying the central revision priorities. We have used the specific points below to guide the revision; the overall assessment is not addressed with a separate substantive argument.",
        "Revised manuscript location: The detailed responses and corresponding changes are provided in R2-1 through R2-10.",
    ]
    for i, comment in enumerate(r2, 1):
        response, location = R2_RESPONSE_EN[i]
        lines.extend([f"R2-{i}", f"Comment: {comment}", f"Response: {response}", f"Revised manuscript location: {location}"])
    lines.extend([
        "Thank you again for the careful review and for the concrete recommendations on comparison design, benchmark validation, statistical interpretation, and external validity.",
        "Responses to Reviewer #3",
        "Overall assessment",
        f"Comment: {r3overall}",
        f"Response: We appreciate this careful evaluation of the separation between language-model interpretation and numerical energy calculation. We have used the specific points below to make the boundary, reproducibility record, and scope conditions more explicit; the overall assessment is not addressed with a separate substantive argument.",
        "Revised manuscript location: The detailed responses and corresponding changes are provided in R3-1 through R3-16.",
    ])
    for i, comment in enumerate(r3, 1):
        response, location = R3_RESPONSE_EN[i - 1]
        lines.extend([f"R3-{i}", f"Comment: {comment}", f"Response: {response}", f"Revised manuscript location: {location}"])
    lines.extend([
        "Thank you again for your thoughtful comments. We also thank the editorial team and all reviewers for their time and care, and respectfully submit the revised manuscript for the Energy Virtual Special Issue of Advanced Engineering Informatics.",
        "Sincerely, Yanhong Zhong (Corresponding Author)",
    ])
    return lines


def build_chinese(r1a: str, r1: list[str], r2overall: str, r2: list[str], r3overall: str, r3: list[str]) -> list[str]:
    lines = [
        "致编辑和审稿人的回复",
        "尊敬的主编、副编辑和各位审稿人：",
        "衷心感谢编辑部和各位审稿人给予我们修改稿件 ADVEI-D-26-08441 的机会。稿件题目为《A decision-time validation framework for LLM-assisted energy studies: One-hour upward-reserve sizing》。我们认真阅读了每一条意见，并围绕决策时信息边界验证、基准独立性、随机服务的可复现性以及备用策略比较中的共同可靠性约束组织本轮修改。",
        "本次修订材料面向 Advanced Engineering Informatics（AEI）的能源虚拟专题（Energy Virtual Special Issue，VSI）。修订稿仍契合该专题，因为论文把能源研究请求、结构化工程计划、决策时信息、确定性数值执行和不确定性下的备用决策连接起来。稿件明确这一范围，并把经验发现与需要形式化保证的论断分开表述。",
        "本轮已完成的离线修改如下。",
        "（1）建立了结构化表单、受约束生成、函数调用、有限状态处理和更强确定性解析器的同条件比较协议。上述依赖服务或额外实现的比较暂作为协议保留，当前结果使用现有证据。",
        "（2）补充了基准构建、标注字段、请求集来源和独立评估设计记录。",
        "（3）归档了现有模型和应用程序接口元数据，并将当前服务证据标为单次响应证据。重复托管服务评估、新模型或应用程序接口调用及其不确定性估计暂列为后续工作，当前结果不包含这些新增数据。",
        "（4）完成了离线澄清闭环分析，量化了 41 个歧义案例所代表的工作量，并追踪了已接受请求字段到数值计算输入的变化。",
        "（5）区分了经验滚动窗口覆盖率与形式化保形保证，并在施加共同经验覆盖率要求后比较备用策略。",
        "（6）加强了能源系统文献背景、公开数据验证、季节和极端爬坡分析、人工审批说明以及范围条件。真实操作员审批和新的外部标注仍作为协议保留，因为它们需要追加数据收集。",
        "因此，当前材料已经包含论文、补充材料、回复信、源文件包和编译程序的全部离线修改。外部 API 调用及其他实时数据收集活动已与已完成证据明确分开。",
        "标记稿使用蓝色文字表示新增内容、红色删除线表示删除内容，并在实质修改处使用蓝色审稿意见标签。未标记稿包含清洁的修订文本。下文完整复现每位审稿人的每条意见，并给出对应的具体回复和稿件位置。",
        "对审稿人 #1 的回复",
        "感谢您围绕决策时信息边界和硬覆盖率约束提出的集中意见。我们同意，这两点都应在方法定义和备用策略比较中明确呈现。",
        "R1-1",
        "审稿意见原文：" + r1[0],
        "中文直译：不同于现有电力系统大语言模型智能体研究主要关注面向调度的输出约束，我们的请求验证层在数值备用计算之前执行决策时信息边界检查，以阻止时间泄漏和含糊默认值。",
        "回复：" + R1_RESPONSE_ZH[0][0],
        "稿件位置：" + R1_RESPONSE_ZH[0][1],
        "R1-2",
        "审稿意见原文：" + r1[1],
        "中文直译：单纯最小化平均成本可能导致经验覆盖率不足，因此实际备用规划需要明确施加硬覆盖率约束，即使这会带来更高的平均备用采购成本。",
        "回复：" + R1_RESPONSE_ZH[1][0],
        "稿件位置：" + R1_RESPONSE_ZH[1][1],
        "再次感谢您对信息边界和可靠性要求提出的准确指导。",
        "对审稿人 #2 的回复",
        "总体意见",
        "审稿意见原文：" + r2overall,
        "中文直译：稿件提出一个决策时验证框架，将自然语言能源研究请求转换为结构化计划，在执行前实施确定性检查，并将被接受的请求连接到一小时向上备用计算。研究涵盖四项大语言模型服务上的 200 条请求测试、组件移除实验、滚动起点备用评估、保形校准、区域迁移分析和资源分配示例。强调防止未来信息泄漏和无依据数值论断具有价值。不过，当前稿件把大语言模型请求验证和备用校准优化两个相对独立的研究结合在一起，却没有展示足够强的端到端因果联系。此外，请求基准由作者设计，尚未证明相对于更简单的结构化接口具有优势；在时间依赖且自适应选择的设置下，报告的经验覆盖率不应被解释为正式的保形保证。因此建议大修。",
        "回复：感谢您对稿件作出的平衡评价，并指出核心修改方向。我们已用下列具体意见指导修订；总体意见本身不再单独作实质性辩解。",
        "稿件位置：具体修改和对应位置见 R2-1 至 R2-10。",
    ]
    for i, comment in enumerate(r2, 1):
        response, location = R2_RESPONSE_ZH[i - 1]
        lines.extend([
            f"R2-{i}",
            "审稿意见原文：" + comment,
            "中文直译：" + R2_COMMENT_TRANSLATION[i - 1],
            "回复：" + response,
            "稿件位置：" + location,
        ])
    lines.extend([
        "再次感谢您对比较设计、基准验证、统计解释和外部有效性提出的细致建议。",
        "对审稿人 #3 的回复",
        "总体意见",
        "审稿意见原文：" + r3overall,
        "中文直译：稿件对语言模型解释和数值能源计算进行了有价值的区分。尤其是防止大语言模型直接生成备用数值，并要求所有数值论断来自确定性计算层，是一个有力的设计选择。不过，仍有若干问题需要澄清。",
        "回复：感谢您对语言模型解释与数值能源计算之间边界的认真评价。我们已用下列具体意见进一步明确边界、可复现记录和范围条件；总体意见本身不再单独作实质性辩解。",
        "稿件位置：具体修改和对应位置见 R3-1 至 R3-16。",
    ])
    for i, comment in enumerate(r3, 1):
        response, location = R3_RESPONSE_ZH[i - 1]
        lines.extend([
            f"R3-{i}",
            "审稿意见原文：" + comment,
            "中文直译：" + R3_COMMENT_TRANSLATION[i - 1],
            "回复：" + response,
            "稿件位置：" + location,
        ])
    lines.extend([
        "再次感谢您的深入意见。我们也感谢主编、副编辑和各位审稿人的时间与指导，谨提交修订稿供 Advanced Engineering Informatics 能源虚拟专题审阅。",
        "此致，Yanhong Zhong（Corresponding Author）",
    ])
    return lines


def build_docx(lines: list[str], output: Path, chinese: bool) -> None:
    doc = Document(str(TEMPLATE))
    body = doc._element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)
    for index, line in enumerate(lines):
        make_paragraph(doc, line, chinese, first=(index == 0))
    doc.core_properties.title = lines[0]
    doc.core_properties.author = "Yanhong Zhong"
    output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output))


def main() -> None:
    r1_first, r1, r2overall, r2, r3overall, r3 = extract_comments()
    english = build_english(r1_first, r1, r2overall, r2, r3overall, r3)
    chinese = build_chinese(r1_first, r1, r2overall, r2, r3overall, r3)
    en_txt = ARTICLE / "Response_to_Reviewers_AEI_R1_EN.txt"
    zh_txt = ARTICLE / "Response_to_Reviewers_AEI_R1_CN.txt"
    write_text(en_txt, english)
    write_text(zh_txt, chinese)
    en_docx = SUBMIT / "Response_to_Reviewers_AEI_R1_EN.docx"
    zh_docx = SUBMIT / "Response_to_Reviewers_AEI_R1_CN.docx"
    build_docx(english, en_docx, False)
    build_docx(chinese, zh_docx, True)
    build_docx(english, ARTICLE / en_docx.name, False)
    build_docx(chinese, ARTICLE / zh_docx.name, True)
    print(en_docx)
    print(zh_docx)


if __name__ == "__main__":
    main()
