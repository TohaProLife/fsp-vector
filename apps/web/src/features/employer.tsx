"use client";
import { useState, useEffect, useRef } from "react";
import { useSearchParams } from "next/navigation";
import {
  Building2,
  Check,
  Plus,
  ArrowRight,
  Sparkles,
  Search,
  ShieldCheck,
  Send,
  SlidersHorizontal,
  GitCompareArrows,
  Eye,
  LockKeyhole,
  Target,
  FileText,
  ChevronDown,
  X,
  Download,
} from "lucide-react";
import {
  api,
  post,
  patch,
  Dict,
  Need,
  items,
  money,
  date,
  specName,
  gradeName,
  specLabels,
  evidenceLabel,
  evidenceScore,
  evidenceVerified,
  explanationText,
} from "@/lib/api";
import { useResource } from "@/lib/hooks";
import { fspProvenance } from "@/lib/fsp-provenance";
import {
  PageTitle,
  Button,
  Field,
  Loading,
  ErrorBox,
  Modal,
  Badge,
  Notice,
  Empty,
  Tag,
  Avatar,
} from "@/components/ui";
import type { WorkspaceContext } from "@/components/workspace";
import { OfferForm } from "./hiring";
const split = (s: unknown) =>
  String(s || "")
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
const specs = Object.entries(specLabels).filter(
  ([id]) => id !== "data_analytics",
);
const grades = ["intern", "junior", "middle", "senior"];
const salaryExpectation = (preferences?: Dict) => {
  const from = Number(preferences?.salary_from || 0);
  const to = Number(preferences?.salary_to || 0);
  if (from > 0 && to > 0) return `${money(from)} — ${money(to)} ₽`;
  if (from > 0) return `от ${money(from)} ₽`;
  if (to > 0) return `до ${money(to)} ₽`;
  return "Зарплатные ожидания не указаны";
};
const matchIndex = (score: unknown) =>
  typeof score === "number" && Number.isFinite(score)
    ? `${Math.round(score)} / 100`
    : "Индекс не рассчитан";
export function CompanyEditor(ctx: WorkspaceContext) {
  const { data, error, loading, reload } =
    useResource<Dict>("/employer/company");
  const [busy, setBusy] = useState(false);
  const [mutationError, setMutationError] = useState<unknown>();
  if (loading) return <Loading />;
  if (error !== undefined)
    return <ErrorBox error={error} retry={() => void reload()} />;
  if (!data) return null;
  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setBusy(true);
    setMutationError(undefined);
    const f = new FormData(e.currentTarget);
    try {
      await patch("/employer/company", Object.fromEntries(f.entries()));
      ctx.notify("Профиль компании сохранён");
      await reload();
    } catch (e) {
      setMutationError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <PageTitle
        eyebrow="Ваша сторона знакомства"
        title="Профиль компании"
        description="Помогите специалистам понять, кто вы и над чем работаете."
      />
      <div className="linear-detail-layout v-form-layout">
        <div className="linear-detail-main">
          <form onSubmit={submit} className="form-stack">
            <div className="row bottom-gap v-company-identity">
              <span className="company-symbol">
                {(data.name || "В").slice(0, 1)}
              </span>
              <div>
                <h3 className="no-margin">{data.name || "Ваша команда"}</h3>
                <small className="muted">Так компанию увидят специалисты</small>
              </div>
            </div>
            <div className="form-grid">
              <Field label="Название компании">
                <input
                  name="name"
                  required
                  defaultValue={data.name || ""}
                  maxLength={160}
                />
              </Field>
              <Field label="Сайт компании">
                <input
                  name="website"
                  type="url"
                  defaultValue={data.website || ""}
                  placeholder="https://…"
                />
              </Field>
              <Field label="Отрасль">
                <input
                  name="industry"
                  defaultValue={data.industry || ""}
                  placeholder="Продуктовая разработка"
                />
              </Field>
              <Field label="Город">
                <input
                  name="city"
                  defaultValue={data.city || ""}
                  placeholder="Москва"
                />
              </Field>
            </div>
            <Field label="О компании и продукте">
              <textarea
                name="description"
                defaultValue={data.description || ""}
                required
                maxLength={6000}
                placeholder="Что создаёте? Как устроена команда?"
              />
            </Field>
            <Field
              label="Контакт для кандидатов"
              hint="Кандидат увидит этот контакт в приглашении ещё до принятия."
            >
              <input
                name="contact"
                defaultValue={data.contact || ""}
                required
                placeholder="talent@company.ru или @recruiter"
                maxLength={300}
              />
            </Field>
            {mutationError !== undefined && <ErrorBox error={mutationError} />}
            <div>
              <Button type="submit" busy={busy}>
                Сохранить компанию <Check size={15} />
              </Button>
            </div>
          </form>
        </div>
        <aside className="linear-properties">
          <h2>Свойства компании</h2>
          <div className="list-row">
            <span>Регистрация</span>
            <Badge>Самостоятельная</Badge>
          </div>
          <div className="list-row">
            <span>Контакт</span>
            <span>{data.contact || "Не указан"}</span>
          </div>
          <p>
            Описание и контакт компании обязательны в предложении. Укажите
            конкретные задачи, условия и следующий шаг — специалисту будет проще
            принять решение.
          </p>
          <Notice>
            Это самостоятельная регистрация компании. Платформа пока не
            подтверждает её юридический статус.
          </Notice>
        </aside>
      </div>
    </>
  );
}
export function Needs(ctx: WorkspaceContext) {
  const { data, error, loading, reload } = useResource<Dict>("/employer/needs");
  const [editing, setEditing] = useState<Dict | null>(null);
  const [blueprint, setBlueprint] = useState<Need | null>(null);
  const [search, setSearch] = useState("");
  if (loading) return <Loading />;
  if (error !== undefined)
    return <ErrorBox error={error} retry={() => void reload()} />;
  const allNeeds = items<Need>(data);
  const list = allNeeds.filter((need) => needMatchesSearch(need, search));
  return (
    <>
      <PageTitle
        eyebrow="От потребности к подборке"
        title="Что нужно команде"
        description="Одна потребность — единый контекст сравнения кандидатов."
        action={
          <Button onClick={() => setEditing({})}>
            <Plus size={15} /> Новая потребность
          </Button>
        }
      />
      {allNeeds.length > 0 && (
        <div className="filters linear-list-toolbar">
          <div className="search-input">
            <Search size={16} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="Поиск потребностей"
              placeholder="Название, команда, специализация"
            />
          </div>
          <small className="muted">
            Показано {list.length} из {allNeeds.length}
          </small>
          {search && (
            <Button variant="ghost" onClick={() => setSearch("")}>
              Сбросить поиск
            </Button>
          )}
        </div>
      )}
      {list.length ? (
        <div className="linear-record-list v-opportunity-list">
          <div className="linear-group-heading">
            <Target size={15} />
            <h2>Потребности команды</h2>
            <span>{list.length}</span>
          </div>
          {list.map((n) => (
            <article
              key={n.id}
              className="linear-record-row v-opportunity-card v-need-card"
            >
              <div className="linear-record-content v-opportunity-body">
                <h3>{n.title}</h3>
                <p>{n.team || n.description?.slice(0, 180)}</p>
                <p className="v-opportunity-meta">
                  <span>{specName(n.specialization)}</span>
                  <span>{gradeName(n.grade)}</span>
                </p>
                <div className="tags v-required-skills">
                  {(n.required_skills || []).slice(0, 6).map((s) => (
                    <Tag key={s}>Обязательно: {s}</Tag>
                  ))}
                  {(n.skills || [])
                    .filter((s) => !n.required_skills?.includes(s))
                    .slice(0, 3)
                    .map((s) => (
                      <Tag key={s}>{s}</Tag>
                    ))}
                </div>
              </div>
              <div className="linear-record-actions v-opportunity-footer">
                <Button variant="secondary" onClick={() => setBlueprint(n)}>
                  План проверки
                </Button>
                <Button variant="secondary" onClick={() => setEditing(n)}>
                  Изменить
                </Button>
                <a
                  className="button primary"
                  href={`/workspace/matches?need=${n.id}`}
                >
                  Подобрать <ArrowRight size={15} />
                </a>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="panel">
          <Empty
            title={
              allNeeds.length
                ? "Потребности не найдены"
                : "Сформулируйте первую потребность"
            }
            text={
              allNeeds.length
                ? "Попробуйте другое название, команду или специализацию."
                : "Какие задачи будет решать человек? Какие навыки обязательны? Добавьте контекст — и получите объяснимую подборку."
            }
            icon="spark"
            action={
              <Button
                onClick={() =>
                  allNeeds.length ? setSearch("") : setEditing({})
                }
              >
                {allNeeds.length ? "Сбросить поиск" : "Создать потребность"}{" "}
                <Plus size={15} />
              </Button>
            }
          />
        </div>
      )}
      {editing && (
        <NeedEditor
          value={editing}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null);
            await reload();
            ctx.notify("Потребность сохранена");
          }}
        />
      )}
      {blueprint && (
        <NeedBlueprint need={blueprint} onClose={() => setBlueprint(null)} />
      )}
    </>
  );
}

function needMatchesSearch(need: Need, search: string) {
  const query = search.trim().toLocaleLowerCase("ru-RU");
  return (
    !query ||
    [need.title, need.team, need.specialization, specName(need.specialization)]
      .filter(Boolean)
      .join(" ")
      .toLocaleLowerCase("ru-RU")
      .includes(query)
  );
}

function NeedBlueprint({ need, onClose }: { need: Need; onClose: () => void }) {
  const { data, loading, error, reload } = useResource<Dict>(
    `/employer/needs/${need.id}/assessment-blueprint`,
  );
  return (
    <Modal title={`План проверки: ${need.title}`} onClose={onClose}>
      {loading ? (
        <Loading />
      ) : error !== undefined ? (
        <ErrorBox error={error} retry={() => void reload()} />
      ) : (
        <div className="form-stack">
          <Notice>
            Практика по потребности содержит {data?.item_count} заданий. Она не
            присваивает глобальную категорию. Реализация языка или framework не
            считается измеренной по общим вопросам.
          </Notice>
          <div className="row">
            <Badge>{specName(data?.specialization)}</Badge>
            <Badge>Контекст: {gradeName(data?.grade)}</Badge>
          </div>
          {(data?.competencies || []).map((c: Dict) => (
            <div className="settings-row" key={c.id}>
              <div>
                <h3>{c.label}</h3>
                <p>
                  {c.priority === "required"
                    ? "Обязательная тема"
                    : c.priority === "preferred"
                      ? "Желательная тема"
                      : "Общий план категории"}{" "}
                  · {c.item_count} задания
                </p>
                <p>
                  Проверяемая часть:{" "}
                  {(c.measurable_skills || []).join(", ") ||
                    "Нет точного измерения запрошенного навыка"}
                </p>
              </div>
            </div>
          ))}
          <h3>Навыки вне области измерения</h3>
          <div className="tags">
            {(data?.unmeasured_skills || []).length ? (
              data?.unmeasured_skills.map((skill: string) => (
                <Tag key={skill}>{skill}</Tag>
              ))
            ) : (
              <Badge>
                Все запрошенные навыки покрыты ограниченной рубрикой
              </Badge>
            )}
          </div>
          <ul className="feedback-list">
            {(data?.limitations || []).map((line: string) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      )}
    </Modal>
  );
}
function NeedEditor({
  value,
  onClose,
  onSaved,
}: {
  value: Dict;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [draft, setDraft] = useState<Dict>(value);
  const [text, setText] = useState("");
  const [extracting, setExtracting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [citations, setCitations] = useState<Dict[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const extract = async () => {
    setExtracting(true);
    setError(undefined);
    try {
      const r = await post("/employer/needs/extract", { text });
      setDraft({
        ...draft,
        ...(r.draft || r.extracted || r.need || r),
        description: text,
      });
      setCitations(
        r.source_spans || r.spans || r.citations || r.entities || [],
      );
      setWarnings(r.warnings || []);
    } catch (e) {
      setError(e);
    } finally {
      setExtracting(false);
    }
  };
  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    const f = new FormData(e.currentTarget);
    const body = {
      title: f.get("title"),
      description: f.get("description"),
      specialization: f.get("specialization"),
      grade: f.get("grade"),
      skills: split(f.get("skills")),
      required_skills: split(f.get("required_skills")),
      salary_from: Number(f.get("salary_from")),
      salary_to: Number(f.get("salary_to")),
      work_format: f.get("work_format"),
      employment: f.get("employment"),
      team: f.get("team"),
    };
    try {
      value.id
        ? await patch(`/employer/needs/${value.id}`, body)
        : await post("/employer/needs", body);
      onSaved();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      wide
      title={value.id ? "Уточнить потребность" : "Новая потребность команды"}
      description="Опишите работу. Подбор опирается на подтверждённые компетенции и выбранные условия."
      onClose={onClose}
    >
      <div className="grid-equal">
        <div>
          <div className="notice">
            <Sparkles size={17} />
            <span>
              Начните с текста — система предложит структуру. Проверьте
              результат перед сохранением.
            </span>
          </div>
          <textarea
            className="top-gap"
            aria-label="Описание потребности для разбора"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Ищем Middle backend-разработчика в финтех: Python, SQL и REST API обязательны. Kafka будет плюсом. Удалённо, 180–240 тысяч рублей."
            style={{ minHeight: 200 }}
          />
          <Button
            className="top-gap"
            variant="secondary"
            busy={extracting}
            disabled={text.trim().length < 10}
            onClick={() => void extract()}
          >
            <Sparkles size={15} /> Разобрать потребность
          </Button>
          {citations.length > 0 && (
            <div className="top-gap">
              <h3>Основания извлечения</h3>
              {citations.slice(0, 8).map((c, i) => (
                <p key={i}>
                  <Badge>
                    {(
                      {
                        specialization: "Направление",
                        grade: "Уровень",
                        skill: "Навык",
                        work_format: "Формат",
                        salary: "Зарплата",
                        employment: "Занятость",
                        required_skills: "Обязательно",
                        skills: "Навыки",
                      } as Record<string, string>
                    )[c.field] ||
                      c.skill ||
                      "Контекст"}
                  </Badge>{" "}
                  {c.quote || c.text || c.source_text}
                </p>
              ))}
            </div>
          )}
          {warnings.map((w, i) => (
            <p className="muted" key={i}>
              {w}
            </p>
          ))}
        </div>
        <form
          key={JSON.stringify(draft)}
          onSubmit={submit}
          className="form-stack"
        >
          <Field label="Название потребности">
            <input
              name="title"
              required
              defaultValue={draft.title || ""}
              maxLength={160}
              placeholder="Backend-разработчик в продуктовую команду"
            />
          </Field>
          <Field label="Задачи и контекст">
            <textarea
              name="description"
              required
              defaultValue={draft.description || ""}
              maxLength={6000}
            />
          </Field>
          <div className="form-grid">
            <Field label="Специализация">
              <select
                name="specialization"
                defaultValue={draft.specialization || "backend"}
              >
                {specs.map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Подтверждённый грейд">
              <select name="grade" defaultValue={draft.grade || "middle"}>
                {grades.map((g) => (
                  <option key={g} value={g}>
                    {gradeName(g)}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Field
            label="Обязательные навыки"
            hint="Через запятую. В карточке видно, какие из них подтверждены."
          >
            <input
              name="required_skills"
              defaultValue={(draft.required_skills || []).join(", ")}
              placeholder="Python, SQL, REST API"
            />
          </Field>
          <Field label="Желательные навыки">
            <input
              name="skills"
              defaultValue={(draft.skills || []).join(", ")}
              placeholder="Docker, Redis"
            />
          </Field>
          <Field label="Команда">
            <input
              name="team"
              defaultValue={draft.team || ""}
              placeholder="Платежи · 8 человек"
            />
          </Field>
          <div className="form-grid">
            <Field label="Зарплата от, ₽">
              <input
                name="salary_from"
                type="number"
                min={0}
                defaultValue={draft.salary_from || 180000}
              />
            </Field>
            <Field label="Зарплата до, ₽">
              <input
                name="salary_to"
                type="number"
                min={0}
                defaultValue={draft.salary_to || 240000}
              />
            </Field>
            <Field label="Формат">
              <select
                name="work_format"
                defaultValue={draft.work_format || "remote"}
              >
                <option value="remote">Удалённо</option>
                <option value="hybrid">Гибрид</option>
                <option value="office">В офисе</option>
                <option value="any">Любой</option>
              </select>
            </Field>
            <Field label="Занятость">
              <select
                name="employment"
                defaultValue={draft.employment || "full_time"}
              >
                <option value="full_time">Полная</option>
                <option value="part_time">Частичная</option>
                <option value="project">Проектная</option>
              </select>
            </Field>
          </div>
          {error !== undefined && <ErrorBox error={error} />}
          <Button busy={busy} type="submit">
            Сохранить потребность <Check size={15} />
          </Button>
        </form>
      </div>
    </Modal>
  );
}
export function Talent(ctx: WorkspaceContext & { saved?: boolean }) {
  const params = useSearchParams();
  const needs = useResource<Dict>("/employer/needs");
  const [needId, setNeedId] = useState(params.get("need") || "");
  const [needSearch, setNeedSearch] = useState("");
  const [query, setQuery] = useState("");
  const [specialization, setSpecialization] = useState("");
  const [grade, setGrade] = useState("");
  const [skill, setSkill] = useState("");
  const [fspOnly, setFspOnly] = useState(false);
  const [format, setFormat] = useState("");
  const [list, setList] = useState<Dict[]>([]);
  const [match, setMatch] = useState<Dict | null>(null);
  const [runs, setRuns] = useState<Dict[]>([]);
  const [runsError, setRunsError] = useState<unknown>();
  const [runsLoading, setRunsLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [categories, setCategories] = useState<Dict[] | null>(null);
  const [categoriesError, setCategoriesError] = useState<unknown>();
  const [categoriesLoading, setCategoriesLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>();
  const [selected, setSelected] = useState<string[]>([]);
  const [compare, setCompare] = useState(false);
  const [detail, setDetail] = useState<Dict | null>(null);
  const [detailError, setDetailError] = useState<unknown>();
  const [offer, setOffer] = useState<Dict | null>(null);
  const listGeneration = useRef(0);
  const detailGeneration = useRef(0);
  const categoriesGeneration = useRef(0);
  const runsGeneration = useRef(0);
  const loadRuns = async () => {
    const request = ++runsGeneration.current;
    setRunsLoading(true);
    setRunsError(undefined);
    try {
      const response = await api("/employer/matches");
      if (request === runsGeneration.current) setRuns(items(response));
    } catch (e) {
      if (request === runsGeneration.current) setRunsError(e);
    } finally {
      if (request === runsGeneration.current) setRunsLoading(false);
    }
  };
  const filters = {
    q: query,
    specialization,
    grade,
    skill,
    fsp_only: fspOnly,
    work_format: format,
  };
  const fetchCandidates = async (nextPage = 1) => {
    const request = ++listGeneration.current;
    setLoading(true);
    setError(undefined);
    try {
      const p = new URLSearchParams();
      Object.entries(filters).forEach(([k, v]) => {
        if (v) p.set(k, String(v));
      });
      p.set("page", String(nextPage));
      const r = await api(`/employer/candidates?${p}`);
      if (request !== listGeneration.current) return;
      setList(items(r));
      setTotal(r.total || 0);
      setPage(nextPage);
      setSelected([]);
      setMatch(null);
    } catch (e) {
      if (request === listGeneration.current) setError(e);
    } finally {
      if (request === listGeneration.current) setLoading(false);
    }
  };
  const makeMatch = async (refine = false) => {
    if (!needId) return;
    const request = ++listGeneration.current;
    // A saved match carries its own immutable need snapshot. Selecting a
    // different need must create a new match, never refine that old snapshot.
    const prior = refine && match?.need_id === needId ? match : null;
    setLoading(true);
    setError(undefined);
    try {
      const r = prior
        ? await post(`/employer/matches/${prior.id}/refine`, { filters })
        : await post("/employer/matches", { need_id: needId, filters });
      if (request !== listGeneration.current) return;
      setMatch(r);
      setList(items(r));
      setTotal(r.total || items(r).length);
      setSelected([]);
      void loadRuns();
      ctx.notify(
        prior ? "Уточнённая подборка сохранена" : "Подборка сохранена",
      );
    } catch (e) {
      if (request === listGeneration.current) setError(e);
    } finally {
      if (request === listGeneration.current) setLoading(false);
    }
  };
  useEffect(() => {
    if (ctx.saved) void loadRuns();
    void fetchCandidates();
    return () => {
      listGeneration.current++;
      detailGeneration.current++;
      categoriesGeneration.current++;
      runsGeneration.current++;
    };
  }, []);
  const openDetail = async (candidate: Dict) => {
    const request = ++detailGeneration.current;
    setDetailError(undefined);
    setDetail({ ...candidate, _loading: true });
    try {
      const response = await api(`/employer/candidates/${candidate.id}`);
      if (request === detailGeneration.current) setDetail(response);
    } catch (e) {
      if (request !== detailGeneration.current) return;
      setDetailError(e);
      setDetail((current) =>
        current?.id === candidate.id
          ? { ...current, _loading: false, _loadFailed: true }
          : current,
      );
    }
  };
  const closeDetail = () => {
    detailGeneration.current++;
    setDetail(null);
    setDetailError(undefined);
  };
  const openCategories = async () => {
    const request = ++categoriesGeneration.current;
    setCategories([]);
    setCategoriesLoading(true);
    setCategoriesError(undefined);
    try {
      const response = await api("/employer/categories");
      if (request === categoriesGeneration.current)
        setCategories(items(response));
    } catch (e) {
      if (request === categoriesGeneration.current) setCategoriesError(e);
    } finally {
      if (request === categoriesGeneration.current) setCategoriesLoading(false);
    }
  };
  const openRun = async (id: string) => {
    const request = ++listGeneration.current;
    setLoading(true);
    setError(undefined);
    try {
      const run = await api(`/employer/matches/${id}`);
      if (request !== listGeneration.current) return;
      setMatch(run);
      setList(items(run));
      setTotal(run.total ?? items(run).length);
      setSelected([]);
      setNeedId(run.need_id);
      const applied = run.filters || {};
      setQuery(applied.q || "");
      setSpecialization(applied.specialization || "");
      setGrade(applied.grade || "");
      setSkill(applied.skill || "");
      setFspOnly(applied.fsp_only === true);
      setFormat(applied.work_format || "");
    } catch (e) {
      if (request === listGeneration.current) setError(e);
    } finally {
      if (request === listGeneration.current) setLoading(false);
    }
  };
  const candidateList = list.map((r) =>
    r.candidate ? { ...r.candidate, _match: r } : r,
  );
  const selectedCandidates = candidateList.filter((c) =>
    selected.includes(c.id),
  );
  const toggle = (id: string) =>
    setSelected((s) =>
      s.includes(id)
        ? s.filter((x) => x !== id)
        : s.length < 3
          ? [...s, id]
          : s,
    );
  const selectedNeed = items<Need>(needs.data).find((n) => n.id === needId);
  const availableNeeds = items<Need>(needs.data);
  const visibleNeeds = availableNeeds.filter(
    (need) => need.id === needId || needMatchesSearch(need, needSearch),
  );
  const candidateGroups = Array.from(
    new Set(
      candidateList.map((candidate) => candidate.specialization || "other"),
    ),
  ).map((specialization) => ({
    specialization,
    candidates: candidateList.filter(
      (candidate) => (candidate.specialization || "other") === specialization,
    ),
  }));
  return (
    <>
      <PageTitle
        eyebrow={
          ctx.saved
            ? "Контекст, который сохраняется"
            : "Подтверждённые навыки, открытые возможности"
        }
        title={
          ctx.saved
            ? "Специалисты для вашей задачи"
            : "Найдите своего специалиста"
        }
        description="Сравнивайте навыки и их основания. Каждый специалист управляет доступом к своим контактам."
        action={
          <Button variant="secondary" onClick={() => void openCategories()}>
            <ShieldCheck size={15} />
            Категории
          </Button>
        }
      />
      {ctx.saved && (
        <div className="linear-list-toolbar linear-need-selection">
          <Target size={16} />
          <div>
            <h3>Выберите потребность команды</h3>
            <input
              value={needSearch}
              onChange={(e) => setNeedSearch(e.target.value)}
              aria-label="Поиск потребности для подбора"
              placeholder="Найти по названию или команде"
              disabled={loading || needs.loading}
            />
            <select
              value={needId}
              disabled={loading || needs.loading}
              onChange={(e) => {
                setNeedId(e.target.value);
                setMatch(null);
                setList([]);
                setTotal(0);
                setSelected([]);
                setError(undefined);
              }}
              aria-label="Потребность для подбора"
            >
              <option value="">Выберите потребность</option>
              {visibleNeeds.map((n) => (
                <option key={n.id} value={n.id}>
                  {n.title} · {gradeName(n.grade)}
                </option>
              ))}
            </select>
            <small className="muted">
              Показано {visibleNeeds.length} из {availableNeeds.length}
              {selectedNeed &&
              needSearch &&
              !needMatchesSearch(selectedNeed, needSearch)
                ? " · выбранная потребность сохранена"
                : ""}
            </small>
            {needSearch && (
              <button className="link-action" onClick={() => setNeedSearch("")}>
                Сбросить поиск
              </button>
            )}
          </div>
          <Button
            busy={loading}
            disabled={!needId || needs.loading || needs.error !== undefined}
            onClick={() => void makeMatch()}
          >
            <Sparkles size={15} /> Подобрать
          </Button>
        </div>
      )}
      {ctx.saved && needs.loading && <Loading label="Загружаем потребности" />}
      {ctx.saved && needs.error !== undefined && (
        <ErrorBox error={needs.error} retry={() => void needs.reload()} />
      )}
      <form
        className="filters linear-list-toolbar"
        onSubmit={(e) => {
          e.preventDefault();
          ctx.saved && needId
            ? void makeMatch(!!match)
            : void fetchCandidates();
        }}
      >
        <div className="search-input">
          <Search />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Навык, специализация, псевдоним"
            aria-label="Поиск специалистов"
          />
        </div>
        <select
          value={specialization}
          onChange={(e) => setSpecialization(e.target.value)}
          aria-label="Специализация"
        >
          <option value="">Все направления</option>
          {specs.map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
        <select
          value={grade}
          onChange={(e) => setGrade(e.target.value)}
          aria-label="Грейд"
        >
          <option value="">Все уровни</option>
          {grades.map((g) => (
            <option key={g} value={g}>
              {gradeName(g)}
            </option>
          ))}
        </select>
        <select
          value={format}
          onChange={(e) => setFormat(e.target.value)}
          aria-label="Формат работы"
        >
          <option value="">Любой формат</option>
          <option value="remote">Удалённо</option>
          <option value="hybrid">Гибрид</option>
          <option value="office">Офис</option>
        </select>
        <input
          value={skill}
          onChange={(e) => setSkill(e.target.value)}
          placeholder="Конкретный навык"
          aria-label="Навык"
          style={{ flex: "0 1 130px" }}
        />
        <label className="check-label">
          <input
            type="checkbox"
            checked={fspOnly}
            onChange={(e) => setFspOnly(e.target.checked)}
          />
          С достижениями ФСП
        </label>
        <Button variant="secondary" type="submit" busy={loading}>
          <SlidersHorizontal size={15} /> Применить
        </Button>
      </form>
      {match && (
        <div className="row between bottom-gap match-context">
          <div>
            <span className="muted">
              Подборка {String(match.id).slice(0, 8)} ·{" "}
              {match.total ?? list.length} специалистов
            </span>
            <p className="safe-data-note no-margin">
              Индекс соответствия навыкам и условиям · Не вероятность найма
            </p>
          </div>
          <Badge tone="purple">
            {match.need?.title || selectedNeed?.title || "Потребность команды"}
          </Badge>
        </div>
      )}
      {error !== undefined && (
        <div className="bottom-gap">
          <ErrorBox error={error} />
        </div>
      )}
      {loading ? (
        <Loading label="Сопоставляем навыки и условия" />
      ) : candidateList.length ? (
        <div className="linear-record-list v-person-list">
          {candidateGroups.map((group) => (
            <section
              className="linear-section"
              key={group.specialization}
              aria-label={specName(group.specialization)}
            >
              <div className="linear-group-heading">
                <ShieldCheck size={15} />
                <h2>{specName(group.specialization)}</h2>
                <span>{group.candidates.length}</span>
              </div>
              {group.candidates.map((c) => (
                <article
                  className={`linear-record-row v-person-card ${selected.includes(c.id) ? "selected" : ""}`}
                  key={c.id}
                >
                  <input
                    type="checkbox"
                    aria-label={`Выбрать ${c.alias} для сравнения`}
                    checked={selected.includes(c.id)}
                    disabled={selected.length >= 3 && !selected.includes(c.id)}
                    onChange={() => toggle(c.id)}
                  />
                  <div className="linear-record-content">
                    <div className="v-person-identity">
                      <Avatar name={c.alias || "Специалист"} size="large" />
                      <div>
                        <h3>
                          <button
                            className="link-action"
                            onClick={() => void openDetail(c)}
                          >
                            {c.alias || "Специалист"}
                          </button>
                        </h3>
                        <p>
                          {gradeName(c.confirmed_grade || c.grade)} ·{" "}
                          {c.preferences?.work_format === "remote"
                            ? "Удалённо"
                            : (
                                {
                                  hybrid: "Гибрид",
                                  office: "В офисе",
                                  any: "Любой формат",
                                } as Record<string, string>
                              )[c.preferences?.work_format] ||
                              "Формат не указан"}
                        </p>
                      </div>
                    </div>
                    {c._match && (
                      <p className="evidence-note">
                        {(c._match.reasons || [])
                          .slice(0, 2)
                          .map((r: unknown) => explanationText(r))
                          .join(" · ") ||
                          "Основания совпадения доступны в профиле"}
                      </p>
                    )}
                  </div>
                  <div className="linear-record-meta v-person-evidence">
                    <div className="tags">
                      {(c.evidence || [])
                        .slice(0, 2)
                        .map((e: Dict, i: number) => (
                          <Tag key={e.id || i} verified={evidenceVerified(e)}>
                            {e.skill ||
                              e.competency_label ||
                              e.label ||
                              e.competency}{" "}
                            · {evidenceLabel(e)}
                          </Tag>
                        ))}
                      {(c.skills || []).slice(0, 2).map((s: string) => (
                        <Tag key={s}>{s} · заявлено</Tag>
                      ))}
                      {c.source === "synthetic_fixture" && (
                        <Badge>Демоданные</Badge>
                      )}
                      {c.fsp?.achievements?.length > 0 && (
                        <Badge tone={fspProvenance(c.fsp).tone}>
                          {fspProvenance(c.fsp).label}
                        </Badge>
                      )}
                    </div>
                    <small className="muted">
                      <LockKeyhole size={12} />{" "}
                      {c.contacts ? "Доступ разрешён" : "Контакты закрыты"}
                    </small>
                  </div>
                  <div className="linear-record-actions v-record-actions">
                    {c._match && (
                      <span title="Индекс соответствия. Не вероятность найма.">
                        <span className="v-match-index">
                          <strong>{matchIndex(c._match.score)}</strong>
                          <small>Соответствие задаче</small>
                        </span>
                      </span>
                    )}
                    <Button
                      variant="secondary"
                      onClick={() => void openDetail(c)}
                    >
                      <Eye size={13} /> Профиль
                    </Button>
                    <Button onClick={() => setOffer(c)}>
                      <Send size={13} /> Пригласить
                    </Button>
                  </div>
                </article>
              ))}
            </section>
          ))}
        </div>
      ) : (
        <div className="panel">
          <Empty
            title="Пока нет подходящих профилей"
            text="Проверьте специализацию, уровень и фильтры. В поиске участвуют только опубликованные профили с подтверждённой категорией."
          />
        </div>
      )}
      {!match && total > 24 && (
        <div className="row between top-gap">
          <small className="muted">
            Показано {(page - 1) * 24 + 1}–{Math.min(page * 24, total)} из{" "}
            {total}
          </small>
          <div className="inline">
            <Button
              variant="secondary"
              disabled={page === 1 || loading}
              onClick={() => void fetchCandidates(page - 1)}
            >
              Предыдущая
            </Button>
            <Button
              variant="secondary"
              disabled={page * 24 >= total || loading}
              onClick={() => void fetchCandidates(page + 1)}
            >
              Следующая
            </Button>
          </div>
        </div>
      )}
      {categories !== null && (
        <Modal
          title="Подтверждённые категории"
          description="Категория объединяет специализацию и грейд. После выбора нажмите «Применить», чтобы обновить выдачу."
          onClose={() => {
            categoriesGeneration.current++;
            setCategories(null);
          }}
        >
          {categoriesLoading ? (
            <Loading label="Загружаем категории" />
          ) : categoriesError !== undefined ? (
            <ErrorBox
              error={categoriesError}
              retry={() => void openCategories()}
            />
          ) : categories.length ? (
            categories.map((c, i) => (
              <div
                className="list-row"
                key={`${c.specialization}-${c.grade}-${i}`}
              >
                <div>
                  <strong>
                    {specName(c.specialization)} · {gradeName(c.grade)}
                  </strong>
                  <small>{c.count || c.total || 0} специалистов</small>
                </div>
                <Button
                  variant="ghost"
                  onClick={() => {
                    setSpecialization(c.specialization);
                    setGrade(c.grade);
                    categoriesGeneration.current++;
                    setCategories(null);
                  }}
                >
                  Выбрать <ArrowRight size={14} />
                </Button>
              </div>
            ))
          ) : (
            <Empty
              title="Категорий пока нет"
              text="Они появятся после подтверждения и публикации профилей."
            />
          )}
        </Modal>
      )}
      {ctx.saved &&
        (runsLoading || runsError !== undefined || runs.length > 0) && (
          <div className="linear-section top-gap">
            <div className="panel-header">
              <h2>Сохранённые подборки</h2>
              <Badge>{runs.length}</Badge>
            </div>
            {runsLoading && <Loading label="Обновляем сохранённые подборки" />}
            {runsError !== undefined && (
              <ErrorBox error={runsError} retry={() => void loadRuns()} />
            )}
            {runs.slice(0, 8).map((r) => (
              <div className="list-row" key={r.id}>
                <div>
                  <strong>
                    {r.title ||
                      r.need_title ||
                      r.need?.title ||
                      `Подборка ${r.id.slice(0, 8)}`}
                  </strong>
                  <small>
                    {date(r.created_at)} · Сохранённый контекст подбора
                  </small>
                </div>
                <Button
                  variant="ghost"
                  disabled={loading}
                  onClick={() => void openRun(r.id)}
                >
                  Открыть <ArrowRight size={14} />
                </Button>
              </div>
            ))}
          </div>
        )}
      {selected.length > 0 && (
        <div className="compare-dock">
          <span>Выбрано {selected.length} из 3</span>
          <Button variant="ghost" onClick={() => setSelected([])}>
            Очистить
          </Button>
          <Button
            disabled={selected.length < 2}
            onClick={() => setCompare(true)}
          >
            <GitCompareArrows size={15} /> Сравнить
          </Button>
        </div>
      )}
      {compare && (
        <CompareModal
          candidates={selectedCandidates}
          onClose={() => setCompare(false)}
          onOffer={(c) => {
            setCompare(false);
            setOffer(c);
          }}
        />
      )}
      {detail && (
        <CandidateDetail
          candidate={detail}
          context={candidateList.find((c) => c.id === detail.id)?._match}
          error={detailError}
          onRetry={() => void openDetail(detail)}
          onClose={closeDetail}
          onOffer={() => {
            setOffer(detail);
            closeDetail();
          }}
        />
      )}
      {offer && (
        <OfferForm
          candidate={offer}
          need={selectedNeed}
          onClose={() => setOffer(null)}
          onSaved={() => {
            setOffer(null);
            ctx.notify("Персональное приглашение отправлено");
          }}
        />
      )}
    </>
  );
}
function CandidateDetail({
  candidate: c,
  context,
  error,
  onRetry,
  onClose,
  onOffer,
}: {
  candidate: Dict;
  context?: Dict;
  error?: unknown;
  onRetry: () => void;
  onClose: () => void;
  onOffer: () => void;
}) {
  const breakdownLabels: Record<string, string> = {
    C: "Компетенции",
    T: "Результат экзамена",
    P: "Совместимость условий",
    A: "Свежесть",
    S: "Смысловая близость",
    F: "Достижения ФСП",
    coverage: "Компетенции",
    competencies: "Компетенции",
    assessment: "Результат экзамена",
    preferences: "Условия",
    freshness: "Свежесть",
    semantic:
      context?.semantic_status === "disabled_neutral_constant"
        ? "Текстовая модель отключена"
        : "Сходство текста",
    fsp: "Достижения ФСП",
  };
  return (
    <Modal
      wide
      title={c.alias || "Безопасный профиль"}
      description={`${specName(c.specialization)} · ${gradeName(c.confirmed_grade || c.grade)}`}
      onClose={onClose}
    >
      {c._loading ? (
        <Loading />
      ) : c._loadFailed ? (
        <ErrorBox error={error} retry={onRetry} />
      ) : (
        <div className="linear-detail-layout v-evidence-sheet">
          <div className="linear-detail-main">
            {c.source === "synthetic_fixture" && (
              <Notice>
                Вымышленный профиль из демонстрационного набора. Источник
                каждого свидетельства указан отдельно.
              </Notice>
            )}
            <div className="row bottom-gap v-person-identity v-profile-identity">
              <Avatar name={c.alias} size="large" />
              <div>
                <h2>{c.alias || "Специалист"}</h2>
                <Badge>
                  <ShieldCheck size={11} />
                  Категория в паспорте
                </Badge>
                <p className="no-margin">
                  {specName(c.specialization)} ·{" "}
                  {gradeName(c.confirmed_grade || c.grade)}
                </p>
              </div>
              {context && (
                <Badge tone="purple">{matchIndex(context.score)}</Badge>
              )}
            </div>
            <h3>Подтверждения и наблюдения</h3>
            <div className="evidence-list">
              {(c.evidence || []).map((e: Dict, i: number) => (
                <div className="evidence-row" key={e.id || i}>
                  <span
                    className={
                      evidenceVerified(e) ? "green-icon" : "purple-icon"
                    }
                  >
                    <ShieldCheck size={15} />
                  </span>
                  <div>
                    <strong>
                      {e.label || e.competency_label || e.skill || e.competency}
                    </strong>
                    <small>
                      {evidenceLabel(e)} ·{" "}
                      {date(e.confirmed_at || e.verified_at || e.created_at)}
                    </small>
                  </div>
                  <Badge tone={evidenceVerified(e) ? "green" : "purple"}>
                    {evidenceScore(e) !== null
                      ? Math.round(evidenceScore(e)!)
                      : "Не измерено"}
                  </Badge>
                </div>
              ))}
            </div>
            <h3 className="top-gap">Заявленный стек</h3>
            <div className="tags">
              {(c.skills || []).map((s: string) => (
                <Tag key={s}>{s} · заявлено</Tag>
              ))}
            </div>
            {context?.gaps?.length > 0 && (
              <div className="passport-story">
                <h3>Темы для уточнения</h3>
                <ul className="feedback-list">
                  {context?.gaps.map((g: unknown, i: number) => (
                    <li key={i}>
                      {typeof g === "string"
                        ? g
                        : `${(g as Dict).skill || "Навык"}: ${(g as Dict).message || "Нужно уточнить подтверждение."}`}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <p className="safe-data-note">
              <ShieldCheck size={13} />
              Начальная экспертная шкала. Пилотная калибровка ещё не измерена;
              грейд не подтверждает длительный опыт эксплуатации.
            </p>
          </div>
          <div className="linear-properties">
            <div className="passport-story" style={{ marginTop: 0 }}>
              <h3>Условия кандидата</h3>
              <p>
                {c.preferences?.work_format === "remote"
                  ? "Удалённо"
                  : (
                      {
                        hybrid: "Гибрид",
                        office: "В офисе",
                        any: "Любой формат",
                      } as Record<string, string>
                    )[c.preferences?.work_format] || "Не указано"}{" "}
                ·{" "}
                {c.preferences?.employment === "full_time"
                  ? "Полная занятость"
                  : (
                      {
                        part_time: "Частичная занятость",
                        project: "Проектная работа",
                        any: "Любая занятость",
                      } as Record<string, string>
                    )[c.preferences?.employment] || "Занятость не указана"}
                <br />
                {salaryExpectation(c.preferences)}
              </p>
            </div>
            {context && (
              <>
                <h3 className="top-gap">Почему этот профиль</h3>
                <ul className="feedback-list">
                  {(context.reasons || []).map((r: unknown, i: number) => (
                    <li key={i}>{explanationText(r)}</li>
                  ))}
                </ul>
                <div className="evidence-breakdown">
                  {Object.entries(context.breakdown || {}).map(([key, v]) => {
                    const value =
                      typeof v === "number"
                        ? v
                        : ((v as Dict)?.points ??
                          (v as Dict)?.contribution ??
                          (v as Dict)?.value ??
                          0);
                    return (
                      <div key={key} className="list-row">
                        <span>{breakdownLabels[key] || key}</span>
                        <strong>{Number(value).toFixed(1)}</strong>
                      </div>
                    );
                  })}
                </div>
              </>
            )}
            {c.contacts ? (
              <div className="top-gap">
                <Notice tone="green">
                  Контакты открыты вашей компании по согласию кандидата.
                </Notice>
                <div className="passport-story">
                  <p>
                    <strong>Имя:</strong> {c.name}
                  </p>
                  {Object.entries(c.contacts)
                    .filter(([, v]) => v)
                    .map(([k, v]) => (
                      <p key={k}>
                        <strong>{k}</strong>: {String(v)}
                      </p>
                    ))}
                </div>
              </div>
            ) : (
              <p className="safe-data-note">
                <LockKeyhole size={15} />
                Имя и контакты откроются именно вашей компании по явному
                разрешению кандидата при принятии приглашения или
                самостоятельном отклике.
              </p>
            )}
            <div className="top-gap">
              <Button onClick={onOffer}>
                <Send size={15} /> Отправить приглашение
              </Button>
            </div>
            {c.fsp?.achievements?.length > 0 && (
              <div className="top-gap">
                <h3>Достижения ФСП</h3>
                <Badge tone={fspProvenance(c.fsp).tone}>
                  {fspProvenance(c.fsp).label}
                </Badge>
                {c.fsp.achievements.slice(0, 3).map((a: Dict, i: number) => (
                  <p key={i}>
                    {a.event_name || a.title || a.name} ·{" "}
                    {a.place ? `${a.place} место` : "Участие"}
                  </p>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}
function CompareModal({
  candidates,
  onClose,
  onOffer,
}: {
  candidates: Dict[];
  onClose: () => void;
  onOffer: (c: Dict) => void;
}) {
  return (
    <Modal
      wide
      title="Сравнить основания"
      description="Одинаковый контекст, прозрачные совпадения и неизвестные темы."
      onClose={onClose}
    >
      <div className="comparison-table-wrap">
        <table className="comparison-table">
          <thead>
            <tr>
              <th>Основание</th>
              {candidates.map((c) => (
                <th key={c.id}>
                  <Avatar name={c.alias} />
                  <h3>{c.alias}</h3>
                  <Badge>{gradeName(c.confirmed_grade || c.grade)}</Badge>
                  {c.source === "synthetic_fixture" && (
                    <Badge>Демоданные</Badge>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Специализация</td>
              {candidates.map((c) => (
                <td key={c.id}>{specName(c.specialization)}</td>
              ))}
            </tr>
            <tr>
              <td>Индекс соответствия</td>
              {candidates.map((c) => (
                <td key={c.id}>
                  {c._match ? (
                    <Badge tone="purple">{matchIndex(c._match.score)}</Badge>
                  ) : (
                    "Потребность не выбрана"
                  )}
                </td>
              ))}
            </tr>
            <tr>
              <td>Свидетельства</td>
              {candidates.map((c) => (
                <td key={c.id}>
                  <div className="tags">
                    {(c.evidence || []).map((e: Dict, i: number) => (
                      <Tag key={i} verified={evidenceVerified(e)}>
                        {e.label ||
                          e.skill ||
                          e.competency_label ||
                          e.competency}
                        {" · "}
                        {evidenceLabel(e)}
                      </Tag>
                    ))}
                  </div>
                </td>
              ))}
            </tr>
            <tr>
              <td>Заявлено</td>
              {candidates.map((c) => (
                <td key={c.id}>
                  <div className="tags">
                    {(c.skills || []).map((s: string) => (
                      <Tag key={s}>{s}</Tag>
                    ))}
                  </div>
                </td>
              ))}
            </tr>
            <tr>
              <td>Уточнить</td>
              {candidates.map((c) => (
                <td key={c.id}>
                  {(c._match?.gaps || []).map(explanationText).join(" · ") ||
                    (c._match
                      ? "Запрошенные темы подтверждены"
                      : "Потребность не выбрана")}
                </td>
              ))}
            </tr>
            <tr>
              <td>Условия</td>
              {candidates.map((c) => (
                <td key={c.id}>
                  {(
                    {
                      remote: "Удалённо",
                      hybrid: "Гибрид",
                      office: "В офисе",
                      any: "Любой формат",
                    } as Record<string, string>
                  )[c.preferences?.work_format] || "Не указаны"}
                  <br />
                  {salaryExpectation(c.preferences)}
                </td>
              ))}
            </tr>
            <tr>
              <td>Следующий шаг</td>
              {candidates.map((c) => (
                <td key={c.id}>
                  <Button onClick={() => onOffer(c)}>
                    <Send size={13} /> Пригласить
                  </Button>
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
      <p className="safe-data-note">
        <LockKeyhole size={13} />
        Контакты открываются именно вашей компании по явному разрешению
        кандидата при принятии приглашения или самостоятельном отклике.
        Отсутствие подтверждения темы означает, что она не измерена.
      </p>
    </Modal>
  );
}
