from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import zipfile

from lxml import etree

from prepare_human_evidence import read_csv, write_json
from run_paired_services import PROJECT
from positive_reply_content import revise_pairs
from substantive_reply_content import revise_substantive_pairs
from online_reply_content import revise_online_pairs

SPEC = importlib.util.spec_from_file_location("original_response", PROJECT / "src" / "build_aei_r1_response.py")
ORIGINAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ORIGINAL)
TEMPLATE = PROJECT / "article" / "templates" / "Response_to_reviewers_template.docx"
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
BODY_TAG = "{" + NS["w"] + "}body"
TEXT_TAG = "{" + NS["w"] + "}t"
PARAGRAPH_TAG = "{" + NS["w"] + "}p"
RUN_TAG = "{" + NS["w"] + "}r"


def response_pairs() -> dict[str, tuple[str, str]]:
    pairs = {
        "R1-1": ("感谢您指出决策时信息边界的关键作用。我们已在方法定义、框架图和讨论中明确验证层对时间信息、显式字段、数值证据与审批的检查，并加入同字段、同规则的结构化表单、有限状态流程、确定性解析器、JSON模式和函数调用对照。48条独立请求各重复五次的接口对照中，混元三种接口均记录0次不应执行却进入就绪状态；混元决策准确率由JSON对象的0.663提高到JSON模式的0.833和函数调用的0.904。新增结果区分字段解释与固定规则的作用。", "Thank you for identifying the role of the decision-time information boundary. We have clarified the checks of temporal information, explicit fields, numerical evidence, and authorization in the method, framework figure, and Discussion. We have added structured forms, a finite-state workflow, a deterministic parser, JSON-schema requests, and function calling with matched fields and rules. Across 48 independent requests with five trials per interface, the three Hunyuan interfaces recorded zero unsafe-ready cases; decision accuracy increased from 0.663 with JSON objects to 0.833 with JSON schema and 0.904 with function calling. These results separate field interpretation from fixed validation."),
        "R1-2": ("我们同意您的观点，并已采用共同可靠性约束。公开数据中的八种策略均在同一个选择期接受0.95覆盖率筛选和非负偏移校准，随后报告留出测试期的覆盖率、成本和尾部缺额。正文同时报告物理MW量和无量纲成本，避免用不一致的可靠性水平支持成本结论。", "We agree with your view and have adopted a common reliability constraint. All eight public-data policies receive the same 0.95 selection-coverage requirement and nonnegative offset calibration. We then report coverage, cost, and tail shortfall on the held-out test period. Physical MW quantities and dimensionless cost are reported together so that cost conclusions have a defined reliability context."),
        "R2-1": ("感谢您提出同条件对照的建议，我们已采纳。新增48条独立请求上的JSON对象、支持的JSON模式与函数调用比较，每条重复五次；同时实现更完整的确定性解析器，以及24条请求、三位专家输入的72份结构化表单和有限状态流程。结果分别报告决策准确率、严格结构有效率、有效请求就绪率、错误执行就绪率、澄清率、延迟和token消耗。混元的JSON模式与函数调用准确率分别为0.833和0.904，JSON对象为0.663；两项配对比较的Holm校正概率均小于0.001。补充材料列出模式、规则、服务设置、token用量与阻断结果。现有记录中的资源指标为服务商返回的token用量和延迟；账单金额与开发维护工时属于本轮归档指标之外。表单包含人工输入负担，专家时间为自报估计。我们据此将语言模型的作用限定为结构化请求生成与字段解释。", "Thank you for recommending matched comparisons; we decided to adopt this suggestion. We added JSON-object, supported JSON-schema, and function-calling comparisons on 48 independent requests, with five trials per request. We also implemented a more complete deterministic parser, 72 structured forms entered by three experts for 24 requests, and a finite-state workflow. Results separately report decision accuracy, exact schema validity, valid-request readiness, unsafe readiness, clarification, latency, and tokens. Hunyuan decision accuracy is 0.833 with JSON schema and 0.904 with function calling, compared with 0.663 with JSON objects; both paired Holm-adjusted probabilities are below 0.001. The supplement reports token usage, latency, false clarification, unsafe-ready cases, and blocked outcomes. The archived resource measures are provider-reported token use and latency; billed amounts and developer maintenance hours fall outside the recorded measures. Forms include human entry and expert time is self-estimated. We therefore describe the language-model contribution as structured request generation and field interpretation."),
        "R2-2": ("我们理解您对基准独立性的关注，并已补充三人独立标注及独立编写请求。三位标注人员来自电力市场运行、电网可靠性和能源预测岗位，对120条冻结盲测请求与48条独立请求分别标注，共504条记录。独立请求由另一运行分析人员按研究准备场景编写，材料将其来源标记为独立研究准备案例；生产调度台工单导出属于本研究样本来源之外。120条样本的一致性为1.000；48条独立请求的Fleiss κ为0.932，三条字段冲突经书面裁决。新增材料记录说明、专业背景、类别分布、生成过程和裁决。九条历史标签与独立标签的差异被保留并按标签版本分别评分。正文将外推范围限定为独立编写的研究请求，并据此报告证据范围。", "We understand the concern about benchmark independence and have added three independent annotations per request and independently authored requests. Annotators from electricity-market operations, grid reliability, and energy forecasting assessed 120 frozen blind requests and 48 independent requests, producing 504 records. An additional operations analyst wrote study-preparation cases; the archive identifies these as independent study-preparation cases, with production work-order exports outside the sample provenance. Agreement is 1.000 on the 120-request sample; Fleiss' kappa is 0.932 on the 48-request set, with three field-conflict cases adjudicated in writing. We report instructions, expertise, class distributions, generation, and adjudication. Nine differences between historical and independent labels are preserved and scored under their respective label versions. The inference scope is restricted to independently authored study-preparation requests."),
        "R2-3": ("我们采纳了重复评估与版本固化的建议，将单次响应改为每请求五次独立试次。协议覆盖200条历史请求和48条独立请求，冻结temperature=0、top-p=1、4096输出token上限及120秒超时。四服务历史联合成功率为DeepSeek 0.772（95%聚类区间0.658--0.885）、Qwen 0.751（0.644--0.858）、ERNIE 0.703（0.587--0.814）和混元0.661（0.588--0.737）。六组配对检验经Holm校正后的p值为0.346--0.938；独立48条请求的联合成功率比较沿用同一配对校正流程。归档保存实际调用日期、完整提示、请求与返回模型标识、端点版本、参数、返回元数据、延迟、token和哈希。混元主评估的1240个正式试次和接口对照的480个正式试次均由完成响应槽位组成；补充材料按计划分母报告，服务恢复摘要同时记录哈希核验状态。", "We adopted repeated evaluation and version freezing by replacing single-response scoring with five independent trials per request and service. The protocol covers 200 historical and 48 independent requests, with temperature 0, top-p 1, a 4096-output-token limit, and a 120-second timeout. Historical joint success is 0.772 for DeepSeek (95% clustered interval 0.658--0.885), 0.751 for Qwen (0.644--0.858), 0.703 for ERNIE (0.587--0.814), and 0.661 for Hunyuan (0.588--0.737). The six paired tests have Holm-adjusted probabilities of 0.346--0.938; the independently authored 48-request comparison uses the same paired correction procedure. The archive preserves requested and returned models, dates, endpoint versions, full prompts, parameters, response identifiers, latency, tokens, and hashes. The 1,240 Hunyuan primary slots and 480 matched-interface slots are represented by completed response records; the supplement reports the planned denominators and the recovery summary records hash verification."),
        "R2-4": ("我们同意区分关键词阻断、歧义识别和歧义解决，并补充了三层证据。对14条独立澄清请求的70次服务试次，初始澄清率为DeepSeek 0.857、Qwen 0.757、ERNIE 0.614和混元0.614；三项所需字段的显式提及召回率分别为1.000、0.760、0.760和0.670。对全部14条请求，我们保留实际初始响应，加入一次预先规定的分析员确认，再执行五次配对终轮评估，确认文本平均379.7字符。历史未完成的14案逐案表列出6条数值诱导案、8条多语言案、4条accept和10条partial-accept标签，以及每案实际触发规则。新增分析保留62条合格请求的完成率分母，并将阻断结果归于固定验证规则。", "We agree that keyword blocking, ambiguity identification, and ambiguity resolution require separate evidence. Across 70 service trials for the 14 independent clarification requests, initial clarification rates are 0.857 for DeepSeek, 0.757 for Qwen, 0.614 for ERNIE, and 0.614 for Hunyuan; recall for explicitly mentioning the three required fields is 1.000, 0.760, 0.760, and 0.670. We preserve every initial response, add one prespecified analyst confirmation, and run five paired terminal trials per request; the confirmation averages 379.7 characters. A case-level table lists the six numerical-induction cases, eight multilingual cases, four accept labels, ten partial-accept labels, and the recorded trigger for each unfinished case. The 62-case completion denominator is retained, and the blocking result is attributed to fixed validation rules."),
        "R2-5": ("我们讨论后采纳了这一建议，并将讨论改为由结果驱动的机制分析。新增的证据包括四服务联合成功率0.772、0.751、0.703和0.661及其聚类区间；德国四个窗口的带宽敏感性结果（平均覆盖率0.967--0.969、平均归一化成本0.01653--0.01656）；以及共同德国目标下九个字段规格的覆盖率、备用MW和成本差。讨论据此分别解释结构有效性、语义识别、澄清负担、区域残差和数值校准的作用。", "We discussed this recommendation and adopted it by reorganizing the Discussion around mechanisms supported by results. The added evidence includes four-service joint-success estimates of 0.772, 0.751, 0.703, and 0.661 with clustered intervals; German bandwidth sensitivity across four windows, with mean coverage from 0.967 to 0.969 and mean normalized cost from 0.01653 to 0.01656; and coverage, reserve in MW, and cost differences for nine controlled field specifications under a common German target. The Discussion uses these results to distinguish structural validity, semantic interpretation, clarification burden, regional residual behavior, and numerical calibration."),
        "R2-6": ("我们讨论后采纳了拓展方法背景的建议，并在正文新增8篇经Crossref DOI元数据核验的文献。Elmachtoub与Grigas、Bertsimas与Kallus两篇讨论预测结果如何进入优化决策；Lim等讨论可解释的多时域非线性表示；Vázquez-Canteli与Nagy讨论需求响应控制；Nikseresht讨论动态氢需求预测；Yin等讨论能源—水系统的耦合规划；Smets等讨论储能决策导向预测；Hai与Ardakanian讨论风险规避能源套利。我们把这8篇文献分别放入预测表示、需求与控制、耦合规划、预测—优化和风险决策五个方法环节，并明确其研究对象与本文备用计算的关系。", "We discussed the recommendation and adopted it by adding eight references whose DOI metadata were verified through Crossref. Elmachtoub and Grigas and Bertsimas and Kallus address how predictions enter optimization decisions; Lim et al. address interpretable nonlinear multi-horizon representation; V{\\'a}zquez-Canteli and Nagy review demand-response control; Nikseresht studies dynamic hydrogen-demand forecasting; Yin et al. study coupled energy--water planning; Smets et al. study decision-focused forecasting for storage; and Hai and Ardakanian study risk-averse energy arbitrage. We place these eight papers in five methodological links—forecast representation, demand and control, coupled planning, predict--optimize integration, and risk-aware decisions—and state how each relates to the reserve calculation in this paper."),
        "R2-7": ("我们同意需要直接追踪请求字段，并新增了22条独立可接受请求的实际服务字段重放。每项服务含110次配对试次，区域、时域和缺额权重直接从结构化计划读取；DeepSeek、Qwen、ERNIE和混元完成率分别为0.645、0.609、0.645和0.518，混元阻断53/110次。完成计划在相同时间戳和参考目标下复现备用序列，成本差为零。九份公开数据控制规格在共同德国目标下量化字段作用：区域改为奥地利使覆盖率降至0.430、成本差升至+0.10153；120/180分钟时域使备用增加207.3/460.2 MW；变量缩减、缺额权重和可靠性要求分别产生+0.00028、+0.00118和+0.00073的成本差。", "We agree that study fields require a direct trace and added actual service-field replay for 22 independently authored accepted requests. Each service has 110 paired trials; region, horizon, and shortfall weight are read directly from the structured plan. Completion rates are 0.645, 0.609, 0.645, and 0.518 for DeepSeek, Qwen, ERNIE, and Hunyuan, with Hunyuan blocking 53 of 110 trials. Completed plans reproduce the reserve series under identical timestamps and reference targets with zero cost difference. Nine controlled public-data specifications quantify field effects under a common German target: changing the region to Austria lowers coverage to 0.430 and raises the cost difference to +0.10153; 120- and 180-minute horizons increase reserve by 207.3 and 460.2 MW; reducing variables, increasing the shortfall weight, and raising required coverage produce cost differences of +0.00028, +0.00118, and +0.00073."),
        "R2-8": ("我们采纳了时间依赖与选择过程的统计建议，并将可靠性统一表述为经验滚动覆盖率。公开实验在训练、校准、选择和测试边界剔除尚未结束的未来目标，报告目标/残差一阶自相关、有效样本量、完整非重叠时域块的最大残差校准、季节和高爬坡覆盖率。新增德国四个窗口的独立带宽分析显示，带宽因子0.5、1.0和2.0的平均ESS为199.6、251.4和255.7，平均归一化成本为0.01653、0.01656和0.01656，四个测试窗均达到0.95覆盖率。块长度1--6个月时，德国成本增益区间保持正值；奥地利区间跨越零。", "We adopted the statistical recommendation on temporal dependence and adaptive selection and use empirical rolling coverage throughout. The public experiment purges unrealized future targets at training, calibration, selection, and test boundaries and reports lag-one target and residual autocorrelation, effective sample size, complete nonoverlapping horizon-block calibration, seasonal coverage, and high-ramp coverage. An independent German bandwidth analysis gives mean ESS values of 199.6, 251.4, and 255.7 and mean normalized costs of 0.01653, 0.01656, and 0.01656 for factors 0.5, 1.0, and 2.0; all four test windows reach 0.95 coverage for each factor. With block lengths of 1--6 months, the German cost-gain interval remains positive, while the Austrian interval spans zero."),
        "R2-9": ("我们采纳公开高分辨率复现的建议。新增德国、奥地利、比利时和荷兰的公开15分钟负荷，来自OPSD归档的ENTSO-E数据，单位MW。四国各12个30天测试窗，共138240个留出决策。材料给出版本、来源、哈希、去重、时间对齐、缺失处理和严格时间切分。公开实验使用已观测负荷与日历，因此数据边界可直接复现。结果同时给出MW备用、缺额、尾部缺额与无量纲成本。围绕天气证据，我们另增2篇经Crossref核验的文献：Taylor与Buizza讨论天气集合预报进入电力需求预测，Fajardo-Barco与Achicanoy-Martínez讨论空间—时间信息进入区域需求预测。现有单机场站天气面板定位为辅助迁移诊断，空间代表性天气属于后续数据扩展范围。货币解释限定为取得本地价格后对目标权重的替换。", "We adopted the recommendation for public high-resolution replication. We added public 15-minute load for Germany, Austria, Belgium, and the Netherlands from the OPSD archive of ENTSO-E data, measured in MW. Twelve 30-day test windows per country supply 138,240 held-out decisions. We provide versions, sources, hashes, deduplication, time alignment, missing-data rules, and chronological splits. Observed load and calendar inputs make the public information boundary directly reproducible. Results include reserve, shortfall, and tail shortfall in MW together with dimensionless cost. We added two separately verified context references: Taylor and Buizza describe weather-ensemble inputs for electricity-demand forecasting, and Fajardo-Barco and Achicanoy-Martinez study spatial-temporal information in regional demand forecasting. The one-airport weather panel remains a secondary transfer diagnostic; spatially representative weather belongs to a subsequent data extension. Monetary interpretation requires replacing the objective weights with local prices."),
        "R2-10": ("我们同意需要共同可靠性条件，已对公开数据中全部八种策略施加同一选择期0.95覆盖率要求和非负偏移，再报告测试期成本、覆盖率与尾部风险。测试期覆盖率逐窗保留；德国选定局部校准四个主要窗口的覆盖率为0.968、0.976、0.971和0.959，带宽敏感性中三个因子均有4/4窗口达到0.95。补充材料明确预测器、220次迭代、邻域、收缩网格、41个场景、状态分组、时间切分和缺失规则。资源分配改为补充材料中的说明性核算，数值比较共享时间戳、信息边界和可靠性筛选条件。", "We agree that the comparison needs a common reliability condition. All eight public-data policies receive the same 0.95 selection-coverage requirement and nonnegative offset before test cost, coverage, and tail risk are reported. Test coverage remains listed by window; selected local coverage in the four German bandwidth-study windows is 0.968, 0.976, 0.971, and 0.959, and each of the three bandwidth factors reaches 0.95 in all four windows. The supplement specifies the predictor, 220 iterations, neighborhoods, shrinkage grid, 41 scenarios, state grouping, temporal splits, and missing-data rules. Resource allocation is presented as supplementary illustrative accounting, while the numerical comparisons share timestamps, information boundaries, and reliability screening."),
        "R3-1": ("感谢您认真核对部署表述。我们已加入独立编写的48条研究准备请求、三人独立标注、24条请求的专家计划及书面审批。记录明确这些请求不属于生产调度台工单导出。论文的结论限定为离线研究准备与验证流程，不宣称真实部署有效性。", "Thank you for examining the deployment wording. We added 48 independently authored study-preparation requests, three independent annotations, expert plans, and written reviews for 24 requests. The archive identifies these requests as study-preparation cases rather than production operator work-order exports. Conclusions are limited to the evaluated offline study-preparation and validation workflow, and operational deployment validity is not claimed."),
        "R3-2": ("我们同意版本归档必须永久关联每次评估。新增材料记录请求与返回模型、日期、端点版本、完整提示、参数、响应标识、延迟、token和哈希。初始提交版本与当前服务版本分别保存，使每一项结果都对应实际调用记录。稿件将协议冻结与供应商权重冻结分开表述；若服务端模型发生变化，需要按同一冻结协议重新评估。", "We agree that version records must remain associated with each evaluation. New records preserve requested and returned models, dates, endpoint versions, full prompts, parameters, response identifiers, latency, tokens, and hashes. Original-submission and current-service versions remain separate so every result corresponds to its actual calls. The manuscript distinguishes a frozen evaluation protocol from immutable provider weights; a provider model change requires renewed evaluation under the same protocol."),
        "R3-3": ("我们采纳了重复执行的建议。冻结协议对每项服务、每条请求执行五次独立调用，报告请求内均值、聚类置信区间、每次决策的一致性和配对统计。200条历史请求与48条独立请求使用同一提示与生成参数。最终正式记录的计划试次均完成并通过哈希核验，开发阶段的服务诊断与正式分母分开管理。", "We have adopted repeated execution. The frozen protocol runs five independent calls per request and service and reports within-request means, clustered confidence intervals, decision consistency, and paired statistics. The 200 historical and 48 independent requests share the same instruction and decoding parameters. The finalized formal trial records are complete and hash-verified; development diagnostics are kept separate from the formal denominators."),
        "R3-4": ("感谢您要求明确指标。我们已定义联合成功为同次响应同时通过所有适用的结构、语义、信息、证据、审批、解析和数值来源检查。新增混淆矩阵完整列出accept、clarify、reject、partial accept及无效响应，另报告决策准确率和校验后准确率。48条独立请求的五次重复混淆计数采用240个服务试次；历史200条请求的联合成功率为DeepSeek 0.772、Qwen 0.751、ERNIE 0.703和混元0.661，补充材料同时给出逐类计数。", "Thank you for requesting an explicit definition. Joint success requires the same response to pass every applicable structure, meaning, information, evidence, approval, parsing, and numerical-provenance check. New confusion matrices include accept, clarify, reject, partial accept, and invalid output. Decision accuracy and validated accuracy are reported separately. The independent-request confusion counts use 240 trials per service from 48 requests with five repetitions; the historical 200-request joint-success estimates are 0.772 for DeepSeek, 0.751 for Qwen, 0.703 for ERNIE, and 0.661 for Hunyuan, with class counts provided in the supplement."),
        "R3-5": ("我们采纳了人工专家对照。三位专业人员各自为相同24条请求编制计划，共72份；三人的处置准确率均为1.000，字段准确率分别为1.000、1.000和0.825，均无不安全就绪。自报准备时间均值为2.93至3.25分钟；接口耗时按实际测量报告。两种时间的来源与工作内容不同，不能据此声称语言模型加检查器严格快于专家。", "We have added the human-expert comparison. Three professionals independently prepare plans for the same 24 requests, producing 72 plans; each has disposition accuracy of 1.000, field accuracy of 1.000, 1.000, and 0.825, and zero unsafe-ready cases. Mean self-estimated preparation time ranges from 2.93 to 3.25 minutes, while service latency is measured. The timing sources and work contents differ, so we do not claim that the language-model-plus-checker workflow is strictly faster than experts."),
        "R3-6": ("我们同意这一归因。摘要、方法、结果、讨论与结论统一把未解决默认值阻断归于固定验证层，语言模型负责提出候选字段。配对盲测中，41条需要澄清的请求被固定规则退回，规则违规执行率由0.205降至0.000；新增同规则接口与确定性解析器对照进一步体现这种职责划分。", "We agree with this attribution. The abstract, method, results, Discussion, and conclusion attribute unresolved-default blocking to fixed validation. In the paired blind comparison, 41 clarification-labelled requests were returned by the fixed rule and the rule-violating execution rate fell from 0.205 to 0.000. The language model proposes candidate fields, while matched interfaces and the deterministic parser further clarify this responsibility split."),
        "R3-7": ("感谢您提出澄清负担。我们保留历史41条澄清与48/62完成结果，并分析14条未完成的请求阶段处置。新增14条独立歧义请求的完整配对确认实验，报告每条一次确认、平均379.7字符、终轮接受和就绪率及两次接口耗时；混元终轮就绪率为0.971，两次调用中位耗时为47.26秒。确认文本是预设实验输入，结果用于量化安全、完成率和交互负担，不能替代真实值班澄清。", "Thank you for raising clarification burden. We retain the historical 41 clarification cases and 48/62 completion result and analyze the request-stage dispositions of the 14 unfinished cases. The new paired confirmation experiment covers 14 independent ambiguous requests and reports one confirmation per case, a mean of 379.7 characters, terminal acceptance and readiness, and both-call latency; Hunyuan terminal readiness is 0.971 with a median two-call time of 47.26 seconds. The confirmations are prespecified experimental inputs, so the result quantifies safety, completion, and interaction burden without representing live duty-operator clarification."),
        "R3-8": ("我们同意两部分需要清楚交接。新增22条独立请求的实际服务字段重放，每项服务110次配对试次，已完成的检查计划与人工标注参考的备用序列及成本一致；混元完成57/110次，其余请求在数值执行前被阻断。九份补充研究计划追踪六类字段对目标、预测、校准和报告的变化。方法与讨论明确验证层确定计算的可接受性，数值层产生备用与成本，阻断请求不赋予数值成本。成本改善均归于预测与校准。", "We agree that the two components need a precise hand-off. Actual service-field replay covers 22 independent requests and 110 paired trials per service; completed checked plans reproduce the independently labelled reference reserve series and cost, while Hunyuan completes 57 of 110 trials and blocks the remainder before numerical execution. Nine additional study plans trace six field types through target construction, prediction, calibration, and reporting. The method and Discussion identify validation as the admissibility step and the numerical layer as the source of reserve and cost; blocked requests receive no numerical cost. Cost improvements are attributed to prediction and calibration."),
        "R3-9": ("我们讨论后采纳了拓展需求不确定性背景的建议，并新增8篇经过DOI元数据核验的相关文献。需求与控制方面引用Vázquez-Canteli与Nagy的需求响应综述、Nikseresht的动态氢需求预测；决策方面引用Yin等的能源—水耦合规划、Smets等的储能决策导向预测和Hai与Ardakanian的风险规避套利；方法联系方面引用Lim等、Elmachtoub与Grigas、Bertsimas与Kallus。正文逐一说明这些研究如何把决策时可用信息转化为预测、控制或规划选择，并将本文的请求边界与备用计算放在同一链条中。", "We discussed the recommendation and adopted it by adding eight DOI-verified references. For demand and control, we cite the demand-response review by V{\\'a}zquez-Canteli and Nagy and the dynamic hydrogen-demand study by Nikseresht. For decisions, we cite coupled energy--water planning by Yin et al., decision-focused storage forecasting by Smets et al., and risk-averse arbitrage by Hai and Ardakanian. For methodological links, we cite Lim et al., Elmachtoub and Grigas, and Bertsimas and Kallus. The text explains how each study converts decision-time information into a forecasting, control, or planning choice and places the request boundary and reserve calculation in the same chain."),
        "R3-10": ("我们同意该统计限定，并将全部可靠性结果定义为指定时间切分下的经验覆盖率。新增时间边界目标剔除、自相关、块最大残差校准、季节与高爬坡结果、有效样本量、带宽和块长度敏感性。德国带宽因子0.5--2.0的四个测试窗均达到0.95，德国块长度1--6个月的成本增益区间保持正值；奥地利区间跨越零。正文把这些结果用于经验监测，正式有限样本覆盖结论留给满足相应假设的专门分析。", "We agree with this statistical qualification and define all reliability results as empirical coverage under the stated chronological splits. We added boundary target purging, autocorrelation, block-maximum residual calibration, seasonal and high-ramp results, effective sample size, bandwidth sensitivity, and block-length sensitivity. All four German test windows reach 0.95 for bandwidth factors from 0.5 to 2.0; the German cost-gain interval remains positive across block lengths of 1--6 months, while the Austrian interval spans zero. The manuscript uses these results for empirical monitoring and reserves formal finite-sample coverage claims for analyses whose assumptions are satisfied."),
        "R3-11": ("我们接受共同可靠性比较的建议。公开验证中的八种策略使用同一选择期覆盖率条件与非负偏移，测试期随后统一评价。原0.953与0.937比较已从正文主要成本结论中移出；主表同时展示公共约束下的覆盖、成本与逐窗达标情况，并明确选择期约束不等于所有测试窗达到0.95。", "We have adopted the common-reliability comparison. All eight public-data policies use the same selection-coverage condition and nonnegative offset, followed by common test evaluation. The original 0.953 versus 0.937 comparison has been removed from the main cost conclusion. Main tables show coverage, cost, and the number of qualifying windows under the public comparison, while clarifying that selection screening does not make every test window reach 0.95."),
        "R3-12": ("我们采纳了措辞建议，并将状态打乱统一称为残差状态敏感性诊断。基础预测、评价数据、成本函数、选择期和收缩候选值保持固定；仅对状态坐标进行逐列置换，再比较选择期成本和备用结果。正文将输出解释为指定状态扰动下的敏感性证据，使用条件保持清楚。", "We adopted the wording recommendation and now call state scrambling a residual-state sensitivity diagnostic. The base prediction, evaluation data, cost function, selection block, and shrinkage candidates remain fixed; state coordinates are permuted column by column, followed by comparison of selection cost and reserve results. The manuscript interprets the output as sensitivity evidence under the specified state perturbation and states the conditioning clearly."),
        "R3-13": ("感谢您指出绝对尺度的解释问题。新增公开实验明确负荷与备用单位为MW，并定义成本指数为平均加权备用与缺额除以校准期平均负荷。原匿名数据结果仅为方法连续性记录，不再作经济解释；主要物理与成本权衡使用公开数据表说明，且不转写为市场支付或货币节省。", "Thank you for identifying the scale-interpretation issue. Public experiments specify load and reserve in MW and define the cost index as mean weighted reserve and shortfall divided by calibration-period mean load. Original anonymized results are retained for methodological continuity without economic interpretation. Public tables explain the physical and normalized-cost trade-off, and the index is not presented as a market payment or monetary saving."),
        "R3-14": ("我们采纳了分状态报告。补充材料按四季及训练期80分位近期爬坡阈值定义高爬坡状态，报告各状态样本数、覆盖率、MW备用与成本，并单列预测损失和残差相关。部分状态低于0.95，例如奥地利春季覆盖率0.918、奥地利高爬坡覆盖率0.915；正文保留这些结果并把它们解释为监测和再校准信号。分组仅使用决策时已观测变量。", "We have added conditional reporting. The supplement reports sample counts, coverage, reserve in MW, and cost by season and by high-ramp states defined from the training-period 80th percentile of recent ramps. Prediction loss and residual correlations are reported separately. Some regimes fall below 0.95, including Austria spring at 0.918 and Austria high-ramp at 0.915; the manuscript retains these values as signals for monitoring and recalibration. Groups use variables observed at decision time."),
        "R3-15": ("感谢您要求描述审批流程。新增24条书面审批记录，由备用研究审批岗位依据请求、字段、可用信息规则和证据要求形成，结果为4通过、9退回与11拒绝。材料列明可修改字段、再次送审和授权后状态。论文将这项已取得的书面研究审查与历史布尔门分别表述；记录属于研究包书面审批，现场电子签章和值班签字未采集，现场运行签发继续依组织规程办理。", "Thank you for requesting the approval procedure. A reserve-study reviewer provides 24 written decisions from requests, study fields, information-availability rules, and evidence requirements: four approvals, nine returns, and eleven rejections. Records specify permitted corrections, renewed review, and authorized states. The manuscript distinguishes this completed written study review from the historical Boolean gate; electronic field signatures and duty-operator signatures were not collected, and operational issuance follows the organization's procedures."),
        "R3-16": ("我们认同您对结论边界的建议。结论现围绕已评估能源研究中的请求解释、决策时信息检查、记录审批、确定性数值执行与经验可靠性展开。所有主要结果与独立标注、重复评估或公开计算证据对应。", "We agree with your guidance on scope. The conclusion now covers request interpretation, decision-time information checks, recorded authorization, deterministic numerical execution, and empirical reliability in the evaluated energy studies. Principal findings are linked to independent annotation, repeated evaluation, or public computation."),
    }


    pairs["R2-6"] = ("我们讨论后决定采纳拓展方法背景的建议，并在正文新增8篇经Crossref DOI元数据核验的文献。Elmachtoub与Grigas、Bertsimas与Kallus两篇讨论预测结果如何进入优化决策；Lim等讨论可解释的多时域非线性表示；Vázquez-Canteli与Nagy讨论需求响应控制；Nikseresht讨论动态氢需求预测；Yin等讨论能源—水系统的耦合规划；Smets等讨论储能决策导向预测；Hai与Ardakanian讨论风险规避能源套利。我们把这8篇文献放入预测表示、需求与控制、耦合规划、预测—优化和风险决策五个方法环节，并在第2.1和第2.5节逐项说明其研究对象、信息边界和对本文备用计算设计的启发。", "We discussed the recommendation and decided to adopt it by adding eight references whose DOI metadata were verified through Crossref. Elmachtoub and Grigas and Bertsimas and Kallus address how predictions enter optimization decisions; Lim et al. address interpretable nonlinear multi-horizon representation; V{\\'a}zquez-Canteli and Nagy review demand-response control; Nikseresht studies dynamic hydrogen-demand forecasting; Yin et al. study coupled energy--water planning; Smets et al. study decision-focused forecasting for storage; and Hai and Ardakanian study risk-aware energy arbitrage. Sections 2.1 and 2.5 organize these eight studies into forecast representation, demand and control, coupled planning, predict--optimize integration, and risk-aware decisions, and state the information boundary and reserve-design implication for each link.")
    pairs["R2-9"] = ("我们采纳公开高分辨率复现的建议。新增德国、奥地利、比利时和荷兰的公开15分钟负荷，来自OPSD归档的ENTSO-E数据，单位MW。四国各12个30天测试窗，共138240个留出决策。材料给出版本、来源、哈希、去重、时间对齐、缺失处理和严格时间切分。公开实验使用已观测负荷与日历，因此数据边界可直接复现。结果同时给出MW备用、缺额、尾部缺额与无量纲成本。针对天气空间代表性，另增2篇经Crossref核验的文献，分别讨论天气集合预报进入需求预测、空间—时间信息进入区域需求预测。单机场站天气面板定位为辅助迁移诊断，空间代表性天气属于后续数据扩展范围。货币解释限定为取得本地价格后对目标权重的替换。", "We adopted the recommendation for public high-resolution replication. We added public 15-minute load for Germany, Austria, Belgium, and the Netherlands from the OPSD archive of ENTSO-E data, measured in MW. Twelve 30-day test windows per country supply 138,240 held-out decisions. We provide versions, sources, hashes, deduplication, time alignment, missing-data rules, and chronological splits. Observed load and calendar inputs make the public information boundary directly reproducible. Results include reserve, shortfall, and tail shortfall in MW together with dimensionless cost. For the spatial-weather boundary, we added two Crossref-verified references on weather-ensemble inputs for demand forecasting and spatial-temporal inputs for regional demand forecasting. The single-airport weather panel remains a secondary transfer diagnostic; spatially representative weather belongs to a subsequent data extension. Monetary interpretation requires replacing the objective weights with local prices.")
    pairs["R3-1"] = ("感谢您认真核对部署表述。我们已加入独立编写的48条研究准备请求、三人独立标注、24条请求的专家计划及书面审批，并将研究范围明确为离线研究准备与验证流程。材料中的请求来源为独立研究准备案例，生产运行签发属于组织规程所覆盖的后续环节。", "Thank you for examining the deployment wording. We added 48 independently authored study-preparation requests, three independent annotations, expert plans, and written reviews for 24 requests, and define the study scope as an offline study-preparation and validation workflow. The request archive represents independent study-preparation cases; production issuance belongs to the subsequent organizational operating procedure.")
    pairs["R3-5"] = ("我们采纳了人工专家对照。三位专业人员各自为相同24条请求编制计划，共72份；三人的处置准确率均为1.000，字段准确率分别为1.000、1.000和0.825，均无不安全就绪。自报准备时间均值为2.93至3.25分钟；接口耗时按实际测量报告。两类时间对应不同的准备工作，本文并列报告准确性、字段质量、人工准备时间与服务延迟。", "We adopted the human-expert comparison. Three professionals independently prepare plans for the same 24 requests, producing 72 plans; each has disposition accuracy of 1.000, field accuracy of 1.000, 1.000, and 0.825, and zero unsafe-ready cases. Mean self-estimated preparation time ranges from 2.93 to 3.25 minutes, while service latency is measured separately. The two timing measures cover different preparation tasks, so the manuscript reports accuracy, field quality, human preparation time, and service latency as separate quantities.")
    pairs["R3-7"] = ("感谢您提出澄清负担。我们保留历史41条澄清与48/62完成结果，并分析14条未完成的请求阶段处置。新增14条独立歧义请求的完整配对确认实验，报告每条一次确认、平均379.7字符、终轮接受和就绪率及两次接口耗时；混元终轮就绪率为0.971，两次调用中位耗时为47.26秒。确认文本是预设的分析员脚本输入，本文将其作为信息补全后的终轮证据，并单独标注实际值班对话属于后续验证范围。", "Thank you for raising clarification burden. We retain the historical 41 clarification cases and 48/62 completion result and analyze the request-stage dispositions of the 14 unfinished cases. The new paired confirmation experiment covers 14 independent ambiguous requests and reports one confirmation per case, a mean of 379.7 characters, terminal acceptance and readiness, and both-call latency; Hunyuan terminal readiness is 0.971 with a median two-call time of 47.26 seconds. The confirmations are prespecified analyst-script inputs. We use them as terminal evidence after field completion and identify live duty-operator dialogue as a subsequent validation setting.")
    pairs["R3-9"] = ("我们讨论后决定采纳拓展需求不确定性背景的建议，并在正文新增8篇经Crossref DOI元数据核验的方法与能源决策文献。需求与控制方面引用Vázquez-Canteli与Nagy的需求响应综述、Nikseresht的动态氢需求预测；决策方面引用Yin等的能源—水耦合规划、Smets等的储能决策导向预测和Hai与Ardakanian的风险规避套利；方法联系方面引用Lim等、Elmachtoub与Grigas、Bertsimas与Kallus。针对R2-9提出的天气空间代表性边界，另增2篇经Crossref核验的天气集合预测与空间—时间负荷预测文献。第2.1和第2.5节分别说明预测信息、可用变量、规划目标与控制动作之间的联系，并将本文的请求边界和备用计算放在同一决策链条中。", "We discussed the recommendation and decided to adopt it by adding eight Crossref-verified methodological and energy-decision references. The demand and control context now cites the demand-response review by V{\\'a}zquez-Canteli and Nagy and dynamic hydrogen-demand forecasting by Nikseresht. The decision context cites coupled energy--water planning by Yin et al., decision-focused storage forecasting by Smets et al., and risk-aware arbitrage by Hai and Ardakanian. The methodological links cite Lim et al., Elmachtoub and Grigas, and Bertsimas and Kallus. For the spatial-weather boundary raised in R2-9, we added two separately verified references on weather-ensemble forecasting and spatial-temporal load forecasting. Sections 2.1 and 2.5 connect forecast information, available variables, planning objectives, and control actions, and place the request boundary and reserve calculation in one decision chain.")
    pairs["R3-10"] = ("我们接受该统计限定，并将全部可靠性结果定义为指定时间切分下的经验覆盖率。新增时间边界目标剔除、自相关、块最大残差校准、季节与高爬坡结果、有效样本量、带宽和块长度敏感性。德国带宽因子0.5--2.0的四个测试窗均达到0.95，德国块长度1--6个月的成本增益区间保持正值；奥地利区间跨越零。正文把这些结果用于经验监测，并将有限样本覆盖性质限定在相应假设成立的分析中。", "We accept this statistical qualification and define all reliability results as empirical coverage under the stated chronological splits. We added boundary target purging, autocorrelation, block-maximum residual calibration, seasonal and high-ramp results, effective sample size, bandwidth sensitivity, and block-length sensitivity. All four German test windows reach 0.95 for bandwidth factors from 0.5 to 2.0; the German cost-gain interval remains positive across block lengths of 1--6 months, while the Austrian interval spans zero. The manuscript uses these results for empirical monitoring and confines finite-sample coverage properties to analyses with the corresponding assumptions.")
    pairs["R3-11"] = ("我们采纳共同可靠性比较的建议。公开验证中的八种策略使用同一选择期覆盖率条件与非负偏移，测试期随后统一评价。原0.953与0.937比较已从正文主要成本结论中移出；主表同时展示公共约束下的覆盖、成本与逐窗达标情况，并按可靠性—成本联合结果解释区域差异。", "We adopted the common-reliability comparison. All eight public-data policies use the same selection-coverage condition and nonnegative offset, followed by common test evaluation. The original 0.953 versus 0.937 comparison has been removed from the main cost conclusion. Main tables pair coverage, cost, and the number of qualifying windows, and regional differences are interpreted from this reliability--cost joint result.")
    pairs["R3-13"] = ("感谢您指出绝对尺度的解释问题。新增公开实验明确负荷与备用单位为MW，并定义成本指数为平均加权备用与缺额除以校准期平均负荷。原匿名数据结果用于方法连续性记录；主要物理与成本权衡使用公开数据表说明，成本指数属于内部归一化指标，市场支付与货币节省需要本地价格和结算惩罚参数。", "Thank you for identifying the scale-interpretation issue. Public experiments specify load and reserve in MW and define the cost index as mean weighted reserve and shortfall divided by calibration-period mean load. Original anonymized results are retained for methodological continuity. Public tables explain the physical and normalized-cost trade-off; the cost index is an internal normalized metric, while market payments and monetary savings require local prices and settlement penalties.")
    pairs["R3-15"] = ("感谢您要求描述审批流程。新增24条书面审批记录，由备用研究审批岗位依据请求、字段、可用信息规则和证据要求形成，结果为4通过、9退回与11拒绝。材料列明可修改字段、再次送审和授权后状态。论文将书面研究审查与历史布尔门分别表述；本记录覆盖研究包审批，现场电子签章和值班签字属于组织运行规程的后续环节。", "Thank you for requesting the approval procedure. A reserve-study reviewer provides 24 written decisions from requests, study fields, information-availability rules, and evidence requirements: four approvals, nine returns, and eleven rejections. Records specify permitted corrections, renewed review, and authorized states. The manuscript presents the written study review and the historical Boolean gate as separate records; this dataset covers research-package approval, while electronic field signatures and duty-operator signatures belong to the subsequent organizational operating procedure.")
    r2_6_zh, r2_6_en = pairs["R2-6"]
    pairs["R2-6"] = (r2_6_zh, r2_6_en.replace("by adding eight references", "by adding eight methodological and energy-decision references"))
    r3_9_zh, r3_9_en = pairs["R3-9"]
    pairs["R3-9"] = (
        r3_9_zh.replace("第2.1和第2.5节", "因此本次修订共新增10篇经核验文献，其中8篇服务于方法与能源决策背景，2篇服务于天气与空间代表性边界。第2.1和第2.5节", 1),
        r3_9_en.replace("Sections 2.1 and 2.5 connect", "Thus, the revision adds ten verified references in total: eight for the methodological and energy-decision context and two for the spatial-weather boundary. Sections 2.1 and 2.5 connect", 1),
    )
    evidence_root = PROJECT / "results" / "evidence_completion_20261011"
    reliability_rows = read_csv(evidence_root / "reliability" / "main" / "summary.csv")
    margin_rows = [row for row in reliability_rows if str(row["margin_applied"]).lower() in ("true", "1")]
    qualifying_windows = sum(int(row["windows_meeting_coverage"]) for row in margin_rows)
    minimum_window_coverage = min(float(row["minimum_window_coverage"]) for row in margin_rows)
    dialogue_rows = read_csv(evidence_root / "question_driven_dialogue" / "main" / "dialogue_trials.csv")
    dialogue_stats = {}
    for service in ("deepseek", "qwen", "ernie", "hunyuan"):
        subset = [row for row in dialogue_rows if row["service"] == service]
        times = sorted(float(row["total_service_seconds"]) for row in subset)
        middle = len(times) // 2
        median_seconds = times[middle] if len(times) % 2 else (times[middle - 1] + times[middle]) / 2
        dialogue_stats[service] = {
            "n": len(subset),
            "initial_clarify": sum(row["initial_decision"] == "clarify" for row in subset) / len(subset),
            "matched": sum(int(row["matching_completed_plan"]) for row in subset) / len(subset),
            "median_seconds": median_seconds,
        }
    weather_rows = read_csv(evidence_root / "weather" / "main" / "summary.csv")
    weather_local = {row["input_variant"]: row for row in weather_rows if row["method"] == "Selected shrinkage"}
    pairs["R1-2"] = (
        f"我们讨论后决定采纳共同可靠性约束，并新增冻结裕量的后续经验验证。2019年基准窗口确定非负裕量，随后原样应用于2020年起的8个留出窗口；四国8种策略共{qualifying_windows}个策略—窗口组合全部达到0.95覆盖率，最低逐窗覆盖率为{minimum_window_coverage:.3f}。正文同时报告MW备用、缺额、尾部缺额和无量纲成本，成本比较使用同一选择条件、同一时间边界和同一裕量规则。该结果属于冻结协议下的后续经验检验。",
        f"We discussed your recommendation and decided to adopt a common reliability constraint with a frozen-margin extension. A nonnegative margin was estimated from the 2019 benchmark windows and then applied unchanged to eight held-out windows beginning in 2020. All {qualifying_windows} policy-window combinations across the four countries reached 0.95 empirical coverage, with a minimum window coverage of {minimum_window_coverage:.3f}. The manuscript reports reserve in MW, shortfall, tail shortfall, and dimensionless cost under the same selection rule, information boundary, and margin protocol. This result is an empirical later-window check under the frozen protocol.",
    )
    pairs["R2-4"] = (
        f"我们讨论后决定分开报告关键词阻断、字段提及和追问后的终轮匹配。原14条独立澄清请求的一次确认实验保留每服务70次试次，初始澄清率为DeepSeek 0.857、Qwen 0.757、ERNIE 0.614和混元0.614，所需字段提及召回率为1.000、0.760、0.760和0.670。新增问题驱动追问审计保留280条初始试次，产生421条成功追问响应；只回答前一响应明确追问的字段，最多进行3轮。终轮计划匹配率分别为DeepSeek {dialogue_stats['deepseek']['matched']:.3f}、Qwen {dialogue_stats['qwen']['matched']:.3f}、ERNIE {dialogue_stats['ernie']['matched']:.3f}和混元 {dialogue_stats['hunyuan']['matched']:.3f}，中位总服务时间分别为{dialogue_stats['deepseek']['median_seconds']:.2f}、{dialogue_stats['qwen']['median_seconds']:.2f}、{dialogue_stats['ernie']['median_seconds']:.2f}和{dialogue_stats['hunyuan']['median_seconds']:.2f}秒。终轮匹配要求接受处置、区域、时域、缺额权重和人工审批字段全部正确。",
        f"We discussed your recommendation and decided to separate keyword blocking, field mention, and terminal matching after follow-up questions. The original one-confirmation experiment retains 70 trials per service for 14 independent clarification requests; initial clarification rates are 0.857, 0.757, 0.614, and 0.614 for DeepSeek, Qwen, ERNIE, and Hunyuan, with required-field mention recall of 1.000, 0.760, 0.760, and 0.670. A new question-driven audit retains 280 initial trials and records 421 successful follow-up responses. The analyst supplies only fields explicitly requested by the preceding response, with at most three turns. Terminal-plan matching rates are {dialogue_stats['deepseek']['matched']:.3f}, {dialogue_stats['qwen']['matched']:.3f}, {dialogue_stats['ernie']['matched']:.3f}, and {dialogue_stats['hunyuan']['matched']:.3f}; median total service times are {dialogue_stats['deepseek']['median_seconds']:.2f}, {dialogue_stats['qwen']['median_seconds']:.2f}, {dialogue_stats['ernie']['median_seconds']:.2f}, and {dialogue_stats['hunyuan']['median_seconds']:.2f} s, respectively. Matching requires the accepted disposition, correct region, horizon, shortfall weight, and retained human approval.",
    )
    pairs["R2-9"] = (
        f"我们讨论后决定采纳高分辨率公开复现和空间天气边界的建议。四国公开15分钟负荷提供48个滚动窗口和138240个留出决策。针对空间天气，我们新增德国气象局6个空间分布站点，完成8个30天窗口、每个输入方案23040个决策的诊断。加入温度和相对湿度后，选定局部校准的预测pinball损失由{float(weather_local['load_calendar']['predictor_pinball_loss']):.2f}降至{float(weather_local['distributed_weather']['predictor_pinball_loss']):.2f} MW，成本指数由{float(weather_local['load_calendar']['normalized_cost']):.5f}降至{float(weather_local['distributed_weather']['normalized_cost']):.5f}；逐窗最低覆盖率为{float(weather_local['load_calendar']['minimum_window_coverage']):.3f}和{float(weather_local['distributed_weather']['minimum_window_coverage']):.3f}。该结果把天气扩展的预测收益与可靠性边界同时列出。",
        f"We discussed your recommendation and decided to adopt the public high-resolution replication and spatial-weather boundary. The four-country public load set supplies 48 rolling windows and 138,240 held-out decisions. For spatial weather, we added six geographically distributed German Weather Service stations and completed an eight-window, 30-day diagnostic with 23,040 decisions per input variant. Adding temperature and relative humidity reduces selected-local predictor pinball loss from {float(weather_local['load_calendar']['predictor_pinball_loss']):.2f} to {float(weather_local['distributed_weather']['predictor_pinball_loss']):.2f} MW and the cost index from {float(weather_local['load_calendar']['normalized_cost']):.5f} to {float(weather_local['distributed_weather']['normalized_cost']):.5f}; minimum window coverage is {float(weather_local['load_calendar']['minimum_window_coverage']):.3f} and {float(weather_local['distributed_weather']['minimum_window_coverage']):.3f}. The revision reports the predictive change together with its window-level reliability boundary.",
    )
    pairs["R2-10"] = (
        f"我们讨论后决定采纳共同可靠性比较，并新增冻结裕量的后续窗口验证。2019年基准窗口确定同一非负裕量，2020年起的8个窗口随后统一测试；四国8种策略的{qualifying_windows}个策略—窗口组合全部达到0.95，最低逐窗覆盖率为{minimum_window_coverage:.3f}。成本、备用MW、缺额和尾部缺额均在相同信息边界和选择条件下计算，逐窗结果保留在补充材料。",
        f"We discussed your recommendation and decided to adopt the common-reliability comparison with a frozen-margin extension. One shared nonnegative margin is estimated from the 2019 benchmark windows and applied before testing eight windows beginning in 2020. All {qualifying_windows} policy-window combinations across the four countries reach 0.95 empirical coverage, with a minimum window coverage of {minimum_window_coverage:.3f}. Cost, reserve in MW, shortfall, and tail shortfall use the same information boundary and selection condition, and window-level results remain in the Supplementary Material.",
    )
    pairs["R3-11"] = (
        f"我们讨论后决定采纳共同可靠性比较，并将可靠性筛选与后续测试分开报告。2019年基准窗口确定非负裕量，随后应用于2020年起的8个窗口；四国8种策略共{qualifying_windows}个策略—窗口组合达到0.95，最低逐窗覆盖率为{minimum_window_coverage:.3f}。正文和补充材料同时给出覆盖率、成本、备用MW和逐窗达标数，结论围绕冻结协议下的经验结果展开。",
        f"We discussed your recommendation and decided to adopt the common-reliability comparison with separate reporting of screening and later-window testing. A nonnegative margin estimated from the 2019 benchmark windows is applied to eight windows beginning in 2020. All {qualifying_windows} policy-window combinations across the four countries reach 0.95, with a minimum window coverage of {minimum_window_coverage:.3f}. The manuscript and supplement report coverage, cost, reserve in MW, and window-level qualification counts, and interpret the result as empirical evidence under the frozen protocol.",
    )
    recovery = json.loads((PROJECT / "results" / "hunyuan_recovery_v2" / "summary.json").read_text(encoding="utf-8"))
    pairs["R2-7"] = ("我们同意需要直接追踪请求字段，并新增了22条独立可接受请求的实际服务字段重放。每项服务含110次配对试次，区域、时域和缺额权重直接从结构化计划读取；DeepSeek、Qwen、ERNIE和混元验证完成率分别为0.645、0.609、0.645和0.518，混元阻断53/110次。四个服务合计266次通过验证并进入授权计算阶段，174次停留在计算前，362次形成可解释的候选计划。通过验证的计划在相同时间戳和参考目标下复现备用序列，成本差为零；阻断记录保留为空成本状态。澄清类别包含280次初始试次，预设确认平均379.7个字符，四个服务的初始加终轮服务时间中位数分别为4.12、14.28、33.73和47.26秒。对于字段错误的离线代价，我们在共同德国目标上进行受控替换：区域改为奥地利使覆盖率降至0.430、成本差增加0.10153；120/180分钟时域使备用增加207.3/460.2 MW，成本差分别增加0.00293和0.00660；变量缩减、缺额权重增加和可靠性要求提高产生0.00028、0.00118和0.00073的成本差。正确计划、计算前阻断、澄清负担和字段偏差各自对应独立分母与可复核结果。", "We agree that study fields require a direct trace and added actual service-field replay for 22 independently authored accepted requests. Each service has 110 paired trials; region, horizon, and shortfall weight are read directly from the structured plan. Validation completion rates are 0.645, 0.609, 0.645, and 0.518 for DeepSeek, Qwen, ERNIE, and Hunyuan, with 53 of 110 Hunyuan trials blocked. Across the four services, 266 trials pass validation and enter the authorized calculation stage, 174 remain before numerical execution, and 362 produce a numerically interpretable candidate plan. Validated plans reproduce the reserve series under identical timestamps and reference targets with zero paired cost difference; blocked records retain a blank numerical-cost state. The clarification category contains 280 initial trials, a prespecified confirmation averaging 379.7 characters, and median combined service times of 4.12, 14.28, 33.73, and 47.26 s. To quantify the offline consequence of field errors, we replace fields under a common German target: changing the region to Austria lowers coverage to 0.430 and increases the cost difference by 0.10153; 120- and 180-min horizons increase reserve by 207.3 and 460.2 MW, with cost differences of 0.00293 and 0.00660. Reducing variables, increasing the shortfall weight, and raising the reliability requirement produce cost differences of 0.00028, 0.00118, and 0.00073. Correct plans, pre-computation blocks, clarification burden, and field perturbations therefore have separate denominators and reproducible outcomes.")
    pairs["R2-6"] = (
        "我们讨论后决定采纳您的建议，拓展方法背景，并在正文新增8篇相关文献。第2.1节分别讨论Lim等的多时域预测、Nikseresht的氢需求预测、Vázquez-Canteli与Nagy的需求响应、Yin等的能源—水规划、Elmachtoub与Grigas的决策误差损失、Bertsimas与Kallus的条件随机优化，以及Smets等和Hai与Ardakanian的储能与风险规避套利研究。第2.6节进一步落实3项方法联系：按观测时间区分可用输入；同时评价预测误差、备用成本与缺额；用决策时状态进行条件校准。这些联系具体对应本研究的变量可用性检查、共同可靠性选择条件和6类字段的9份受控计算规格。8篇文献的作者、年份和DOI均已核验，修改后的讨论将研究对象、方法依据和本文实验设计逐项对应。",
        "We discussed your recommendation and decided to adopt it by broadening the methodological background and adding eight references to the manuscript. Section 2.1 discusses multi-horizon forecasting by Lim et al., hydrogen-demand forecasting by Nikseresht, demand response by Vázquez-Canteli and Nagy, energy-water planning by Yin et al., decision-error loss by Elmachtoub and Grigas, conditional stochastic optimization by Bertsimas and Kallus, and storage and risk-averse arbitrage studies by Smets et al. and Hai and Ardakanian. Section 2.6 develops three methodological connections: distinguishing available inputs by observation time; evaluating prediction error, reserve cost, and shortfall together; and conditioning calibration on decision-time states. These connections correspond to our variable-availability checks, common reliability selection requirement, and nine controlled calculation specifications spanning six field categories. We verified the authors, years, and DOIs of all eight references. The revised discussion connects each application and methodological basis with our experimental design."
    )
    pairs["R3-9"] = (
        "我们讨论后决定采纳您的建议，补充需求不确定性与能源决策的研究背景。本轮共新增10篇文献，其中8篇用于方法与能源决策，2篇用于天气集合与空间—时间负荷预测。第2.1节说明需求响应、动态氢需求、能源—水规划、储能预测和风险规避套利的研究对象；第2.6节将其中3项方法依据落实到输入时间、决策目标和条件校准。对应的实验证据包括四国48个滚动测试窗、138240个留出决策，以及6类字段的9份受控计算规格。正文据此同时评价经验覆盖率、MW备用量、缺额和成本，并逐项追踪字段变化的计算后果。全部10篇新增文献均有可核验的DOI记录。",
        "We discussed your recommendation and decided to adopt it by extending the background on demand uncertainty and energy decisions. The revision adds ten references: eight on methodology and energy decisions, and two on weather ensembles and spatial-temporal load forecasting. Section 2.1 describes the applications in demand response, dynamic hydrogen demand, energy-water planning, storage forecasting, and risk-averse arbitrage. Section 2.6 connects three methodological principles with input timing, decision objectives, and conditional calibration. The corresponding experimental evidence comprises 48 rolling test windows in four countries, 138,240 held-out decisions, and nine controlled calculation specifications spanning six field categories. The manuscript jointly evaluates empirical coverage, reserve in MW, shortfall, and cost, and traces each field change to its computed consequence. All ten added references have verifiable DOI records."
    )
    for key, (chinese_text, english_text) in pairs.items():
        chinese_text = chinese_text.replace("均无不安全就绪", "均记录0份错误进入执行就绪状态的计划")
        english_text = english_text.replace("V{\\'a}zquez", "Vázquez")
        english_text = english_text.replace("zero unsafe-ready cases", "zero plans incorrectly marked ready for execution")
        english_text = english_text.replace("unsafe-ready cases", "plans incorrectly marked ready for execution")
        english_text = english_text.replace("unsafe readiness", "incorrect execution readiness")
        pairs[key] = (chinese_text, english_text)
    chinese_text, english_text = pairs["R2-2"]
    pairs["R2-2"] = (
        chinese_text.replace("材料将其来源标记为独立研究准备案例；生产调度台工单导出属于本研究样本来源之外。", "材料记录其独立研究准备案例的来源。"),
        english_text.replace("the archive identifies these as independent study-preparation cases, with production work-order exports outside the sample provenance.", "the archive records their provenance as independent study-preparation cases."),
    )
    chinese_text, english_text = pairs["R2-3"]
    pairs["R2-3"] = (
        chinese_text.replace("均由完成响应槽位组成", "均有对应的完成响应记录"),
        english_text.replace("primary slots", "primary trials").replace("matched-interface slots", "matched-interface trials"),
    )
    chinese_text, english_text = pairs["R3-13"]
    pairs["R3-13"] = (
        chinese_text.replace("内部归一化指标", "以校准期平均负荷为尺度的无量纲指标").replace("平均加权备用与缺额除以校准期平均负荷", "备用与缺额分别按1和20加权后的均值除以校准期平均负荷"),
        english_text.replace("an internal normalized metric", "a dimensionless measure scaled by calibration-period mean load").replace("mean weighted reserve and shortfall", "mean reserve and shortfall weighted by 1 and 20, respectively,"),
    )
    chinese_text, english_text = pairs["R3-2"]
    pairs["R3-2"] = (
        chinese_text + "完成响应清单包含6680条记录：主评估4960条、额外接口对照1440条、澄清终轮280条，每条均关联计划试次与SHA-256哈希。",
        english_text + " The completed-response manifest contains 6,680 records: 4,960 primary, 1,440 additional interface, and 280 terminal clarification records, each linked to its planned trial and SHA-256 hash.",
    )
    chinese_text, english_text = pairs["R3-12"]
    pairs["R3-12"] = (
        chinese_text + "该诊断沿用700天模型拟合、20天校准拟合和10天选择的时间划分，使状态扰动的评价条件可复核。",
        english_text + " The diagnostic retains the chronological split of 700 model-fitting days, 20 calibration-fitting days, and 10 selection days, making its evaluation conditions reproducible.",
    )
    pairs["R3-16"] = (
        "我们认同您对结论范围的建议。第8节总结框架、请求证据和公开备用计算，明确对应168条请求的三人标注、72份专家计划、24条共同请求上的480个服务试次及四国138240个留出决策。德国、比利时和荷兰的平均经验覆盖率为0.954、0.953和0.963。结论围绕已评估能源研究中的请求解释、信息检查、书面授权和数值执行展开。",
        "We agree with your recommendation on scope. Section 8 summarizes the framework, request evidence, and public reserve calculation: three annotations for each of 168 requests, 72 expert plans, 480 service trials on 24 matched requests, and 138,240 held-out decisions in four countries. Mean empirical coverage is 0.954, 0.953, and 0.963 in Germany, Belgium, and the Netherlands. The conclusions cover request interpretation, information checks, written authorization, and numerical execution in the evaluated energy studies.",
    )
    chinese_text, english_text = pairs["R2-6"]
    pairs["R2-6"] = (
        chinese_text.replace("新增8篇相关文献", "新增8篇可核验的相关文献").replace("8篇文献的作者、年份和DOI均已核验，修改后的讨论将研究对象、方法依据和本文实验设计逐项对应。", ""),
        english_text.replace("adding eight references", "adding eight verified references").replace(" We verified the authors, years, and DOIs of all eight references. The revised discussion connects each application and methodological basis with our experimental design.", ""),
    )
    chinese_text, english_text = pairs["R2-7"]
    pairs["R2-7"] = (
        chinese_text.replace("正确计划、计算前阻断、澄清负担和字段偏差各自对应独立分母与可复核结果。", ""),
        english_text.replace(" Correct plans, pre-computation blocks, clarification burden, and field perturbations therefore have separate denominators and reproducible outcomes.", ""),
    )
    chinese_text, english_text = pairs["R3-16"]
    pairs["R3-16"] = (
        chinese_text.replace("结论围绕已评估能源研究中的请求解释、信息检查、书面授权和数值执行展开。", ""),
        english_text.replace(" The conclusions cover request interpretation, information checks, written authorization, and numerical execution in the evaluated energy studies.", ""),
    )
    chinese_text, english_text = pairs["R3-9"]
    pairs["R3-9"] = (
        chinese_text.replace("共新增10篇文献", "共新增10篇可核验文献").replace("正文据此同时评价经验覆盖率、MW备用量、缺额和成本，并逐项追踪字段变化的计算后果。全部10篇新增文献均有可核验的DOI记录。", ""),
        english_text.replace("adds ten references", "adds ten verified references").replace(" The manuscript jointly evaluates empirical coverage, reserve in MW, shortfall, and cost, and traces each field change to its computed consequence. All ten added references have verifiable DOI records.", ""),
    )
    chinese_text, english_text = pairs["R3-4"]
    pairs["R3-4"] = (chinese_text.replace("accept、clarify、reject、partial accept及无效响应", "接受、澄清、拒绝、部分接受及无效响应"), english_text)
    if recovery["main_final_statuses"] != {"success": 1240} or recovery["interface_final_statuses"] != {"success": 480}:
        raise ValueError("Completed-response recovery is incomplete")
    return finalize_response_facts(revise_online_pairs(revise_substantive_pairs(revise_pairs(pairs))))


def finalize_response_facts(pairs: dict[str, tuple[str, str]]) -> dict[str, tuple[str, str]]:
    """Keep the final replies aligned with the reported endpoints and comparisons."""
    def replace_pair(key: str, old_cn: str, new_cn: str, old_en: str, new_en: str) -> None:
        chinese, english = pairs[key]
        if old_cn not in chinese or old_en not in english:
            raise ValueError(f"Response wording changed before factual revision: {key}")
        pairs[key] = chinese.replace(old_cn, new_cn), english.replace(old_en, new_en)

    replace_pair(
        "R2-4",
        "历史14个未完成案例逐案列出处置、类别与触发规则；误澄清、遗漏歧义和隐含字段情形与完整62案分母同时保留。",
        "历史14个未完成案例逐案列出处置、类别与触发规则，并保留48/62的历史完成率。独立请求的误澄清率以25条接受请求的125次试次为分母，漏歧义率以14条澄清请求的70次试次为分母，均按每服务计算。",
        "The 14 historically unfinished cases have case-level dispositions, categories, and trigger rules; false clarification, missed ambiguity, and implicit-field cases retain the complete 62-case denominator.",
        "The historical analysis records the disposition, category, and trigger for each of the 14 unfinished cases and retains the 48/62 completion rate. For the independently authored requests, false clarification uses the 125 trials on 25 accept-labelled requests per service, while missed ambiguity uses the 70 trials on 14 clarify-labelled requests per service.",
    )
    replace_pair(
        "R3-4",
        "混淆矩阵列出接受、澄清、拒绝、部分接受及无效输出，分别报告模型处置与验证后处置。",
        "混淆矩阵列出模型原始处置中的接受、澄清、拒绝、部分接受及无效输出；原始与校验后准确率另行报告。",
        "Confusion matrices report accept, clarify, reject, partial accept, and invalid output, with model and validated dispositions evaluated separately.",
        "Confusion matrices report the original model dispositions: accept, clarify, reject, partial accept, and invalid output. Original and validated accuracy are reported separately.",
    )
    replace_pair(
        "R3-13",
        "原匿名结果在补充材料中保留其相对比较和归一化说明。",
        "补充材料存档原匿名尺度结果及区域内配对成本差。",
        "original anonymized results retain their relative comparisons and normalization in the supplement.",
        "the supplement archives the original anonymized-scale results and paired within-region cost differences.",
    )
    replace_pair(
        "R3-14",
        "补充材料按四季及训练期近期爬坡80分位阈值定义的高爬坡组，分别列出样本量、预测损失、残差相关、覆盖、备用MW和成本。",
        "补充材料按四季及训练期近期爬坡80分位阈值定义的高爬坡组，分别列出样本量、预测pinball损失、校准后覆盖率和成本；目标与残差的时间相关性单独报告。",
        "The supplement reports sample size, prediction loss, residual correlation, coverage, reserve in MW, and cost by season and by high-ramp groups defined using the training-period 80th percentile of recent ramps.",
        "The supplement reports sample size, predictor pinball loss, calibrated coverage, and cost by season and by high-ramp groups defined using the training-period 80th percentile of recent ramps. Temporal correlations of targets and residuals are reported separately.",
    )
    replace_pair(
        "R2-10",
        "各策略共享每个滚动起点的基础预测，计算预算由模型迭代、场景数量及邻域规模给出。",
        "七种非静态策略共享每个滚动起点的基础分位数预测，静态策略采用样本分位数；模型迭代、场景数量及邻域规模给出相应计算预算。残差校准采用前20天，后10天用于选择收缩系数，选择后不在完整30天上重新拟合。",
        "Policies share the base prediction at each rolling origin; iterations, scenario count, and neighborhood size define computational budgets.",
        "The seven non-static policies share the base quantile prediction at each rolling origin, while the static policy uses an empirical quantile; iterations, scenario count, and neighborhood size define the corresponding computational budgets. Residual calibration uses the earlier 20 days, and the later ten days select the shrinkage coefficient, without refitting on all 30 days after selection.",
    )
    for key in ("R2-9", "R3-13"):
        chinese, english = pairs[key]
        pairs[key] = (
            chinese.replace("校准期平均负荷", "前20天校准拟合期的平均负荷"),
            english.replace("calibration-period mean load", "mean load in the earlier 20-day calibration-fitting block"),
        )
    replace_pair(
        "R2-1",
        "增强解析器准确率0.771、执行就绪错误4、延迟0.10毫秒；专家表单处置准确率1.000。",
        "增强解析器准确率0.771，经相同校验器后仍有4次执行就绪错误，延迟0.10毫秒；专家表单处置准确率1.000。",
        "The enhanced parser has accuracy 0.771, four execution-readiness errors and latency 0.10 ms; expert forms have disposition accuracy 1.000.",
        "The enhanced parser has accuracy 0.771, four execution-readiness errors after the same checker, and latency 0.10 ms; expert forms have disposition accuracy 1.000.",
    )
    replace_pair(
        "R2-1",
        "这些结果把自然语言准备的具体内容、字段复用和固定验证分别纳入评价。",
        "原始与校验后处置的配对比较均未显示经Holm校正的接口准确率优势。在24条共同草稿任务中，解析器的处置为24/24正确、字段为39/40正确、可复用输入为52/53。因此，本研究将LLM评价为一种可选的自然语言草拟接口，能够补充当前解析器规则所覆盖的表达，同时保留固定校验和人工复核。",
        "These results evaluate the content of natural-language preparation, field reuse, and fixed validation separately.",
        "Neither the original nor the validated paired comparisons establish a Holm-adjusted interface accuracy advantage over the parser. On the 24-request common draft task, the parser has 24/24 correct dispositions, 39/40 correct fields, and 52/53 reusable inputs. We therefore evaluate the LLM as an optional natural-language drafting interface that can complement the expressions covered by the implemented parser, with fixed validation and human review retained.",
    )
    replace_pair(
        "R3-5",
        "这些对照给出已有专家计划、实际在线草稿、输入替换和完整条件时间的具体证据，每份草稿均保留人工核查与授权要求。",
        "输入复用计数表示保留供核查的参考正确草稿内容，不能直接换算为相对表单或解析器实测节省的时间；共同草稿任务中的解析器已有52/53项可复用输入。总准备时间比较取决于专家自估参照和明确设定的核查、修正及其他任务耗时，每份草稿均保留人工核查与授权要求。",
        "These comparisons supply concrete evidence from existing expert plans, actual online drafts, input replacements, and conditional total time. Every draft retains human verification and authorization.",
        "Input reuse counts reference-correct draft content available for review; it does not directly measure time saved relative to form entry or parsing, and the parser already retains 52/53 inputs on the common draft task. Total preparation-time comparisons depend on the expert self-estimated reference and specified review, correction, and other-task times. Every draft retains human verification and authorization.",
    )
    pairs["R3-6"] = (
        "我们同意应区分解释与校验的作用。200请求的历史配对比较中，新增未决默认值检查使41条歧义请求返回澄清，规则违规执行率由0.205降至0；该变化归于新增的确定性检查。独立48请求的接口比较说明，最终就绪状态同时依赖前端解释与后续校验：解析器的4次就绪错误在相同校验器之后仍然存在，因为其解析与校验器的请求分析共用同一规则词表。所测LLM接口在该比较中记录0次不安全就绪，说明服务输出可以补充这套具体词法规则的不足。正文据此分别说明候选字段解释、固定校验和人工授权的作用。",
        "We agree that interpretation and validation should be distinguished. In the historical paired comparison of 200 requests, the added unresolved-default check returns 41 ambiguous requests for clarification and reduces rule-violating execution from 0.205 to zero; this change is attributable to that deterministic check. The interface comparison on 48 independent requests shows that final readiness depends on both front-end interpretation and subsequent checking: the parser's four readiness errors remain after the same checker because parsing and the checker's request analysis share a rule vocabulary. The evaluated LLM interfaces record zero unsafe-ready trials in this comparison, showing that their outputs can complement this implemented lexical vocabulary. The manuscript therefore distinguishes candidate-field interpretation, fixed validation, and human authorization.",
    )
    replace_pair(
        "R3-1",
        "我们采纳了以独立分析人员请求评价研究范围的建议。",
        "我们增加了由运行分析人员依据研究指引为本研究独立编写的请求，用于评价独立表达下的研究准备。",
        "We adopted evaluation using independently authored analyst requests.",
        "We added requests independently written for this study by an operations analyst using the study instructions, to evaluate study preparation under independently authored wording.",
    )
    replace_pair(
        "R3-15",
        "正文分别说明书面研究审核与历史布尔审批门，各自对应所评价流程中的实际信息和决定。数值程序在字段确认和授权后生成结果证据。",
        "这24份决定是针对冻结请求包实际完成的研究内书面评审；历史重放使用模拟布尔审批门。服务离线重放保留人工授权要求字段，其计算记录不表示每个服务试次均取得独立的现场签章。",
        "The manuscript describes written study review and the historical Boolean approval gate separately, each corresponding to its evaluated information and decisions. The numerical program generates result evidence after field confirmation and authorization.",
        "These 24 decisions were obtained as actual study-specific written reviews of the frozen request packet; the historical replay uses a simulated Boolean approval gate. Offline service replays retain the human-authorization requirement, and their calculation records do not represent separately signed field authorizations for every service trial.",
    )
    for key in ("R2-4", "R3-7"):
        chinese, english = pairs[key]
        pairs[key] = (
            chinese.replace("人工审批", "人工授权要求"),
            english.replace("and human approval", "and the human-authorization requirement"),
        )
    for key in ("R1-2", "R2-10", "R3-11"):
        chinese, english = pairs[key]
        pairs[key] = (
            chinese + "这一协议施加共同的最低可靠性要求，各策略实现的测试覆盖率仍可不同。所选局部策略相对全局校准的平均成本增益约占全局成本的0.13%、0.68%、0.20%和0.81%，依次对应德国、奥地利、比利时和荷兰。",
            english + " This protocol imposes a common minimum reliability requirement; realized test coverage can differ across policies. The selected-local mean cost gains are approximately 0.13%, 0.68%, 0.20%, and 0.81% of global-calibration cost in Germany, Austria, Belgium, and the Netherlands, respectively.",
        )
    return pairs


def lines(chinese: bool) -> list[str]:
    _, r1, overall2, r2, overall3, r3 = ORIGINAL.extract_comments()
    pairs = response_pairs()
    main_labels = dict(re.findall(r"\\newlabel\{([^}]+)\}\{\{([^}]+)\}", (PROJECT / "results" / "manuscript_unmark_build" / "main.aux").read_text(encoding="utf-8")))
    supplement_labels = dict(re.findall(r"\\newlabel\{([^}]+)\}\{\{([^}]+)\}", (PROJECT / "results" / "supplementary_build" / "Supplementary_Material.aux").read_text(encoding="utf-8")))
    evidence_tables = {
        "R1-2": (["public"], ["public_cost_intervals", "common_reliability"]),
        "R2-1": (["interfaces", "nonllm", "expert"], ["interface_tests", "resource_comparison", "recovery"]),
        "R2-2": (["repeat_120", "repeat_48"], []),
        "R2-3": (["repeat_48", "revision_joint"], ["confusion", "usage", "consistency", "paired_tests", "recovery", "joint_revision", "replay_24"]),
        "R2-4": (["clarification"], ["clarification_field", "legacy_dispositions", "question_dialogue"]),
        "R2-7": (["execution"], ["field_trace", "replay_24", "controlled_field_specs"]),
        "R2-8": (["bandwidth_sensitivity"], ["dependence", "conditional", "conditional_prediction", "sensitivity", "bandwidth_revision", "block_length_revision"]),
        "R2-9": (["public", "physical"], ["weather_diagnostic"]),
        "R2-10": (["public", "bandwidth_sensitivity"], ["public_cost_intervals", "bandwidth_revision", "common_reliability"]),
        "R3-3": (["repeat_48", "revision_joint"], ["consistency", "paired_tests", "recovery", "joint_revision"]),
        "R3-4": ([], ["confusion"]),
        "R3-5": (["expert"], []),
        "R3-6": (["interfaces"], []),
        "R3-7": (["clarification"], []),
        "R3-8": (["execution"], ["field_trace"]),
        "R3-10": (["bandwidth_sensitivity"], ["dependence", "conditional", "sensitivity", "bandwidth_revision", "block_length_revision"]),
        "R3-11": (["public"], ["public_cost_intervals", "common_reliability"]),
        "R3-13": (["physical"], []),
        "R3-14": ([], ["conditional", "conditional_prediction"]),
    }
    evidence_tables.update({
        "R1-2": (["frozen_comparison", "frozen_intervals"], ["frozen_all_de_at", "frozen_all_be_nl"]),
        "R2-1": (["interfaces", "nonllm", "expert", "review_workload"], ["api_budgets", "maintenance_specification", "resource_comparison"]),
        "R2-3": (["revision_joint"], ["usage", "consistency", "paired_tests", "api_budgets"]),
        "R2-7": (["execution"], ["execution_accounting", "controlled_field_specs", "question_dialogue"]),
        "R2-10": (["frozen_comparison", "frozen_intervals"], ["frozen_all_de_at", "frozen_all_be_nl"]),
        "R3-5": (["expert", "review_workload"], ["review_workload"]),
        "R3-7": (["clarification"], ["question_dialogue"]),
        "R3-11": (["frozen_comparison", "frozen_intervals"], ["frozen_all_de_at", "frozen_all_be_nl"]),
    })
    evidence_tables.update({
        "R2-1": (["interfaces", "nonllm", "expert", "input_workload", "online_draft_quality"], ["provider_costs", "maintenance_changes", "resource_comparison", "parser_paired_raw", "parser_paired_validated", "online_draft_comparators", "online_draft_resources"]),
        "R2-3": (["revision_joint"], ["usage", "consistency", "paired_tests", "provider_costs"]),
        "R2-7": (["execution", "six_field_execution"], ["field_trace", "six_field_resources_dq", "six_field_resources_eh", "field_faults"]),
        "R3-5": (["expert", "review_workload", "input_workload", "online_draft_quality"], ["matched_validated_quality", "input_workload_interval", "input_workload_classes", "online_draft_stages", "online_draft_comparators", "online_expert_field_difference", "online_draft_resources", "online_time_sensitivity"]),
        "R3-8": (["execution", "six_field_execution"], ["field_trace", "field_faults"]),
    })
    evidence_figures = {
        "R1-1": ["study_framework"],
        "R1-2": ["r1_frozen_policies", "r1_frozen_gains"],
        "R2-1": ["r1_service_interfaces", "r1_draft_preparation"],
        "R2-3": ["r1_service_interfaces"],
        "R2-4": ["r1_clarification"],
        "R2-7": ["r1_field_consequences"],
        "R2-8": ["r1_conditional_bandwidth"],
        "R2-10": ["r1_frozen_policies", "r1_frozen_gains"],
        "R3-3": ["r1_service_interfaces"],
        "R3-5": ["r1_draft_preparation"],
        "R3-6": ["r1_service_interfaces"],
        "R3-7": ["r1_clarification"],
        "R3-8": ["r1_field_consequences"],
        "R3-10": ["r1_conditional_bandwidth"],
        "R3-11": ["r1_frozen_policies", "r1_frozen_gains"],
        "R3-14": ["r1_conditional_bandwidth"],
    }
    if chinese:
        result = ["致编辑和审稿人的回复", "尊敬的主编、副编辑和各位审稿人：",
            "衷心感谢编辑部和三位审稿人给予稿件ADVEI-D-26-08441大修机会。我们认真考虑了全部意见，围绕请求验证、独立证据、服务随机性以及共同可靠性约束完成了本轮修订。",
            "本轮主要修改如下。",
            "（1）补充168条请求的三人独立标注、48条独立编写请求、72份专家计划与24条书面审批。",
            "（2）完成每请求五次重复评估，以及同字段同规则的JavaScript对象表示法（JavaScript Object Notation，JSON）模式、函数调用、表单与确定性解析器比较。",
            "（3）配对澄清包含280个初始试次和421条逐问补全响应，报告字段匹配、追加回复、服务时间、混淆矩阵和多重校正。",
            "（4）加入四国公开15分钟负荷的48个滚动窗口，共138240个留出决策，统一可靠性选择条件并报告以兆瓦（MW）计的物理量。",
            "（5）时间依赖、条件覆盖和参数敏感性与440次计算配对共同评价工作流；256项冻结裕量比较提供同可靠性成本与尾部风险。六字段服务扩展产生196份参考一致的离线计算输出，95项单字段偏差全部返回确认。完整字段草稿协议另有480条初始与54条自动反馈响应，193—200项正确字段和199—260项可复用输入支撑准备质量评价；四服务官方报价、六项维护变更和完整条件时间分析共同评价资源。",
            "我们认为，修改后的稿件仍然契合Advanced Engineering Informatics的能源虚拟专题（Virtual Special Issue，VSI）。本研究连接能源分析请求、决策时信息边界、结构化计划、人工授权与可复现数值决策，体现能源工程信息与计算之间的联系。",
            "标记稿沿用蓝色新增、红色删除线和蓝色审稿标签；清洁稿保留修订后的完整内容。以下逐条保留审稿原文并说明修改位置。"]
    else:
        result = ["Response to the Editor and Reviewers", "Dear Editor-in-Chief, Associate Editor, and Reviewers,",
            "We sincerely thank the editorial team and all three reviewers for the opportunity to revise manuscript ADVEI-D-26-08441. We considered every comment and completed revisions concerning request validation, independent evidence, service stochasticity, and common reliability constraints.",
            "The principal revisions are as follows.",
            "(1) We added three independent annotations for 168 requests, 48 independently authored requests, 72 expert plans, and 24 written reviews.",
            "(2) We completed five-run evaluation per request and matched JavaScript Object Notation (JSON) schema, function-calling, form, and deterministic-parser comparisons.",
            "(3) Paired clarification contains 280 initial trials and 421 question-driven follow-up responses, with field matching, additional replies, service time, confusion matrices, and multiplicity adjustment.",
            "(4) We added 48 rolling windows of public 15-minute load from four countries, comprising 138,240 held-out decisions under common reliability selection rules, with physical quantities in megawatts (MW).",
            "(5) Temporal dependence, conditional coverage, and parameter sensitivity accompany 440 calculation pairs. The 256 frozen-margin outcomes provide common-reliability cost and tail-risk comparisons. The six-field extension yields 196 reference-matched computations, and all 95 single-field deviations return for confirmation. The complete-draft protocol separately adds 480 initial and 54 automatic feedback responses, with 193 to 200 correct fields and 199 to 260 reusable inputs supporting preparation quality. Official tariffs for four services, six maintenance changes, and conditional total time jointly evaluate resources.",
            "We believe that the revised manuscript remains aligned with the Energy Virtual Special Issue (VSI) of Advanced Engineering Informatics. Our study connects energy-study requests, decision-time information boundaries, structured plans, human authorization, and reproducible numerical decisions, addressing the relationship between engineering information and computation.",
            "The marked manuscript retains blue additions, red strikethrough deletions, and blue reviewer labels. The clean manuscript contains the complete revised text. Every reviewer comment is reproduced below with its response and revised location."]
    reviewer_introductions = {
        1: ("感谢您审阅稿件，并关注决策时的信息边界以及备用规划中的可靠性约束。我们围绕这两点说明修改和对应结果。",
            "Thank you for reviewing the manuscript and for your attention to the decision-time information boundary and reliability constraints in reserve planning. We explain the revisions and corresponding results for these two points below."),
        2: ("感谢您全面审阅方法和实验，并提出具体的修改建议。下面逐条说明对应的修改及证据。",
            "Thank you for the comprehensive review of our methods and experiments and for your specific recommendations. We describe the corresponding revisions and evidence for each comment below."),
        3: ("感谢您细致检查研究设计、实验记录和结论范围。下面逐项回复您提出的问题。",
            "Thank you for carefully examining the study design, experimental records, and scope of the conclusions. We respond to each of your questions below."),
    }
    overall_acknowledgments = {
        2: ("感谢您对研究内容的全面评阅，并肯定决策时信息检查的研究价值。您对两部分联系、基准独立性、替代接口和覆盖率解释的意见，帮助我们明确了修订重点。",
            "Thank you for your comprehensive assessment of the study and for recognizing the value of decision-time information checks. Your comments on the connection between the two components, benchmark independence, alternative interfaces, and the interpretation of coverage helped us identify the revision priorities."),
        3: ("感谢您肯定语言模型解释与数值计算的职责划分，并对数值证据来源给予细致评价。您提出的澄清意见对完善稿件很有帮助。",
            "Thank you for recognizing the division of responsibilities between language-model interpretation and numerical calculation and for your careful assessment of numerical provenance. Your requests for clarification have been helpful in improving the manuscript."),
    }
    reviewer_closings = {
        1: ("再次感谢您对信息边界和可靠性要求的提醒，帮助我们更清楚地表述方法及成本比较条件。",
            "Thank you again for drawing our attention to information boundaries and reliability requirements, which helped us express the method and the conditions for cost comparison more clearly."),
        2: ("再次感谢您对方法联系、实验设计和统计解释提出的详细建议，这些意见帮助我们完善研究论证。",
            "Thank you again for your detailed recommendations on methodological connections, experimental design, and statistical interpretation. These comments helped us strengthen the study's argument."),
        3: ("感谢您投入时间核查实验细节与结论表述，也感谢您对数值证据可追溯性的重视。",
            "Thank you for taking the time to examine the experimental details and conclusions, and for your attention to the traceability of numerical evidence."),
    }
    for reviewer, comments, overall in ((1, r1, None), (2, r2, overall2), (3, r3, overall3)):
        result.append(f"对审稿人 #{reviewer} 的回复" if chinese else f"Responses to Reviewer #{reviewer}")
        result.append(reviewer_introductions[reviewer][0 if chinese else 1])
        if overall:
            result.extend(["总体意见" if chinese else "Overall assessment", ("审稿意见原文：" if chinese else "Comment: ") + overall,
                ("回复：" if chinese else "Response: ") + overall_acknowledgments[reviewer][0 if chinese else 1]])
        for index, comment in enumerate(comments, 1):
            key = f"R{reviewer}-{index}"
            result.extend([key, ("审稿意见原文：" if chinese else "Comment: ") + comment])
            if chinese:
                translation = (ORIGINAL.R2_COMMENT_TRANSLATION[index-1] if reviewer == 2 else ORIGINAL.R3_COMMENT_TRANSLATION[index-1] if reviewer == 3 else None)
                if translation:
                    translation = re.sub(r"([\u4e00-\u9fff]) +(?=\d)", r"\1", translation)
                    translation = re.sub(r"(\d) +(?=[\u4e00-\u9fff])", r"\1", translation)
                    result.append("中文直译：" + translation)
            result.append(("回复：" if chinese else "Response: ") + pairs[key][0 if chinese else 1])
            location = "第2–5节、讨论与补充材料中的对应实验表。" if chinese else "Sections 2–5, Discussion, and the corresponding experimental tables in the Supplementary Material."
            if key in ("R2-8","R2-9","R2-10","R3-10","R3-11","R3-13","R3-14"):
                location = "第5节及补充材料：公开实验、共同约束、时间依赖与状态分组。" if chinese else "Section 5 and Supplementary Material: public experiments, common constraints, temporal dependence, and operating regimes."
            if key in ("R2-4","R3-7","R3-15"):
                location = "第4.3节及补充材料：澄清、请求处置与书面审批。" if chinese else "Section 4.3 and Supplementary Material: clarification, request dispositions, and written review."
            specific = {
                "R1-1": ("第2.4–2.5节及第6.1节。", "Sections 2.4–2.5 and 6.1."),
                "R1-2": ("第2.3及5.1节；公开数据策略比较表。", "Sections 2.3 and 5.1; public-data policy comparison table."),
                "R2-1": ("第3.1.1、4.2及6.1节；接口、表单与专家对照表。", "Sections 3.1.1, 4.2, and 6.1; interface, form, and expert comparison tables."),
                "R2-2": ("第3.1及4.1节；补充材料独立请求与标注部分。", "Sections 3.1 and 4.1; supplementary independent-request and annotation study."),
                "R2-3": ("第3.1及4.1节；补充材料重复评估、混淆矩阵、一致性与配对检验表。", "Sections 3.1 and 4.1; supplementary repeated evaluation, confusion, consistency, and paired-test tables."),
                "R2-5": ("第6节讨论。", "Section 6, Discussion."),
                "R2-6": ("第2.1及2.6节文献背景和方法设计；第5.3节字段追踪。", "Sections 2.1 and 2.6, literature context and method design; Section 5.3, field trace."),
                "R2-7": ("第5.3及6.4节；计算重放与字段追踪表。", "Sections 5.3 and 6.4; calculation-replay and field-trace tables."),
                "R3-1": ("第3.1、4.1及7节。", "Sections 3.1, 4.1, and 7."),
                "R3-2": ("第3.1节；补充材料历史模型表与重复协议。", "Section 3.1; supplementary historical-model table and repeated protocol."),
                "R3-3": ("第3.1及4.1节；补充材料一致性与配对检验表。", "Sections 3.1 and 4.1; supplementary consistency and paired-test tables."),
                "R3-4": ("第4.1节；补充材料计分定义及混淆矩阵。", "Section 4.1; supplementary scoring definitions and confusion matrix."),
                "R3-5": ("第4.2节专家配对对照表及第6.2节。", "Section 4.2, matched expert comparison table, and Section 6.2."),
                "R3-6": ("第2.4、4.2及6.1节。", "Sections 2.4, 4.2, and 6.1."),
                "R3-8": ("第5.3及6.4节；计算重放与字段追踪表。", "Sections 5.3 and 6.4; calculation-replay and field-trace tables."),
                "R3-9": ("第2.1及2.6节需求预测与规划文献。", "Sections 2.1 and 2.6, demand-forecasting and planning literature."),
                "R3-12": ("第2.7节及补充材料残差状态敏感性部分。", "Section 2.7 and supplementary residual-state sensitivity study."),
                "R3-16": ("第8节结论。", "Section 8, Conclusions."),
            }
            if key in specific:
                location = specific[key][0 if chinese else 1]
            main_tables, supplementary_tables = evidence_tables.get(key, ([], []))
            if main_tables:
                numbers = ", ".join(main_labels["tab:r1_" + name] for name in main_tables)
                location += (" 正文表" if chinese else " Main manuscript Tables ") + numbers + "."
            if supplementary_tables:
                numbers = ", ".join(supplement_labels["tab:r1_" + name] for name in supplementary_tables)
                location += (" 补充材料表" if chinese else " Supplementary Tables ") + numbers + "."
            figures = evidence_figures.get(key, [])
            if figures:
                numbers = ", ".join(main_labels["fig:" + name] for name in figures)
                figure_word = "Figure" if len(figures) == 1 else "Figures"
                location += (" 正文图" if chinese else f" Main manuscript {figure_word} ") + numbers + "."
            result.append(("稿件位置：" if chinese else "Revised manuscript location: ") + location)
        if not (chinese and reviewer == 3):
            result.append(reviewer_closings[reviewer][0 if chinese else 1])
    if chinese:
        result.append("谨向编辑与三位审稿人再次致谢。Haiwang Zhong（通讯作者）")
    else:
        result.extend(["We again thank the editor and all three reviewers and respectfully submit the revision for the AEI Energy Special Issue.",
            "Sincerely, Haiwang Zhong (Corresponding Author)"])
    if chinese:
        result = [re.sub("策略—窗口(?:组合)?", "策略与窗口组合", paragraph) for paragraph in result]
    return result


def text_of(element) -> str:
    return "".join(element.itertext())


def paragraph_text(element) -> str:
    return "".join(node.text or "" for node in element.findall(".//w:t", NS))


def build(output: Path, content: list[str], chinese: bool) -> None:
    with zipfile.ZipFile(TEMPLATE) as package:
        parts = {entry.filename: package.read(entry.filename) for entry in package.infolist()}
    document = etree.fromstring(parts["word/document.xml"])
    body = document.find("w:body", NS)
    paragraphs = body.findall("w:p", NS)
    def first_matching(predicate):
        return next(paragraph for paragraph in paragraphs if predicate(paragraph_text(paragraph)))

    patterns = {"title": paragraphs[0], "salutation": paragraphs[1], "body": paragraphs[2],
        "summary": first_matching(lambda text: bool(re.match(r"^[（(]\d+[）)]", text))),
        "heading": first_matching(lambda text: text.startswith("Responses to Reviewer")),
        "item": first_matching(lambda text: bool(re.fullmatch(r"R[123]-\d+", text))),
        "comment": first_matching(lambda text: text.startswith("Comment: ")),
        "response": first_matching(lambda text: text.startswith("Response: ")),
        "location": first_matching(lambda text: text.startswith("Revised manuscript location: "))}
    for child in list(body):
        if child.tag != "{" + NS["w"] + "}sectPr":
            body.remove(child)
    for index, line in enumerate(content):
        role = "title" if index == 0 else "salutation" if index == 1 else "body"
        if re.match(r"^[（(]\d+[）)]", line):
            role = "summary"
        elif line.startswith(("Responses to Reviewer", "对审稿人", "Overall assessment", "总体意见")):
            role = "heading"
        elif re.fullmatch(r"R[123]-\d+", line):
            role = "item"
        prefixes = (("Comment: ", "comment"), ("审稿意见原文：", "comment"), ("Response: ", "response"), ("回复：", "response"),
            ("中文直译：", "response"), ("Revised manuscript location: ", "location"), ("稿件位置：", "location"))
        prefix = ""
        for candidate, candidate_role in prefixes:
            if line.startswith(candidate):
                prefix, role = candidate, candidate_role
                break
        paragraph = deepcopy(patterns[role])
        for child in list(paragraph):
            if child.tag != "{" + NS["w"] + "}pPr":
                paragraph.remove(child)
        if chinese:
            properties = paragraph.find("w:pPr", NS)
            if properties is None:
                properties = etree.Element("{" + NS["w"] + "}pPr")
                paragraph.insert(0, properties)
            word_wrap = properties.find("w:wordWrap", NS)
            if word_wrap is None:
                word_wrap = etree.SubElement(properties, "{" + NS["w"] + "}wordWrap")
            word_wrap.set("{" + NS["w"] + "}val", "1")
            kinsoku = properties.find("w:kinsoku", NS)
            if kinsoku is None:
                kinsoku = etree.SubElement(properties, "{" + NS["w"] + "}kinsoku")
            kinsoku.set("{" + NS["w"] + "}val", "1")
            spacing = properties.find("w:spacing", NS)
            if spacing is not None and spacing.get("{" + NS["w"] + "}after"):
                after = int(spacing.get("{" + NS["w"] + "}after"))
                spacing.set("{" + NS["w"] + "}after", str(max(0, after - 10)))
            if prefix == "回复：":
                keep_next = properties.find("w:keepNext", NS)
                if keep_next is None:
                    keep_next = etree.SubElement(properties, "{" + NS["w"] + "}keepNext")
                keep_next.set("{" + NS["w"] + "}val", "1")
            if index == len(content) - 2 and prefix == "稿件位置：":
                keep_next = properties.find("w:keepNext", NS)
                if keep_next is None:
                    keep_next = etree.SubElement(properties, "{" + NS["w"] + "}keepNext")
                keep_next.set("{" + NS["w"] + "}val", "1")
        source_runs = patterns[role].findall("w:r", NS)
        chunks = [(prefix, source_runs[0]), (line[len(prefix):], source_runs[-1])] if prefix else [(line,source_runs[-1])]
        for value, template_run in chunks:
            if not value:
                continue
            run = deepcopy(template_run)
            for child in list(run):
                if child.tag != "{" + NS["w"] + "}rPr":
                    run.remove(child)
            if chinese:
                run_properties = run.find("w:rPr", NS)
                if run_properties is None:
                    run_properties = etree.Element("{" + NS["w"] + "}rPr")
                    run.insert(0, run_properties)
                language = run_properties.find("w:lang", NS)
                if language is None:
                    language = etree.SubElement(run_properties, "{" + NS["w"] + "}lang")
                language.set("{" + NS["w"] + "}val", "zh-CN" if re.search(r"[\u4e00-\u9fff]", value) else "en-US")
                language.set("{" + NS["w"] + "}eastAsia", "zh-CN")
                fonts = run_properties.find("w:rFonts", NS)
                if fonts is not None:
                    fonts.set("{" + NS["w"] + "}eastAsia", "SimSun")
                    fonts.set("{" + NS["w"] + "}hint", "eastAsia")
            node = etree.SubElement(run, TEXT_TAG)
            node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            node.text = value
            paragraph.append(run)
        body.insert(len(body)-1, paragraph)
    parts["word/document.xml"] = etree.tostring(document, encoding="UTF-8", xml_declaration=True, standalone=True)
    if "docProps/core.xml" in parts:
        core = etree.fromstring(parts["docProps/core.xml"])
        for node in core.iter():
            if etree.QName(node).localname == "title":
                node.text = content[0]
            elif etree.QName(node).localname in ("creator", "lastModifiedBy"):
                node.text = "Haiwang Zhong"
        parts["docProps/core.xml"] = etree.tostring(core, encoding="UTF-8", xml_declaration=True, standalone=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for name, data in parts.items():
            package.writestr(name, data)


def main() -> None:
    article = PROJECT / "article"
    audit = []
    for chinese, suffix in ((True,"CN"),(False,"EN")):
        content = lines(chinese)
        filename = "Response_to_Reviewers_AEI_R1_" + suffix + ".docx"
        build(article / filename, content, chinese)
        (article / filename.replace(".docx", ".txt")).write_text("\n\n".join(content), encoding="utf-8")
        with zipfile.ZipFile(TEMPLATE) as original, zipfile.ZipFile(article / filename) as revised:
            preserve = [name for name in original.namelist() if name not in ("word/document.xml", "docProps/core.xml")]
            assert all(original.read(name)==revised.read(name) for name in preserve)
            audit.append({"file": filename, "template_parts_preserved": len(preserve), "reviewer_comments": 28})
    write_json(PROJECT / "results" / "integrated_r1" / "response_template_fidelity.json", {"template_sha256": hashlib.sha256(TEMPLATE.read_bytes()).hexdigest(),
        "font_sizes_preserved": True, "english_template_properties_preserved": True,
        "chinese_east_asian_font": "SimSun",
        "chinese_word_wrap_value": "1", "outputs": audit})
    print(json.dumps(audit,ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
