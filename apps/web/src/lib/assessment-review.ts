export type ReviewIssue = {
  item_id: string | null;
  kind: "missing" | "format" | "limit";
  detail: string;
};
export type ReviewReceipt = {
  answered: number;
  total: number;
  structural_ready: boolean;
  issues: ReviewIssue[];
  public_form_sha256: string | null;
  saved_answers_sha256: string | null;
  prospective_answers_sha256: string | null;
  review_token: string | null;
  limitations: string[];
};
export type CapturedReview = {
  answers: Readonly<Record<string, unknown>>;
  receipt: ReviewReceipt;
  version: number;
};
const sha256 = /^[a-f0-9]{64}$/i;

function plainObject(value: unknown): value is Record<string, unknown> {
  return (
    !!value &&
    typeof value === "object" &&
    [Object.prototype, null].includes(Object.getPrototypeOf(value))
  );
}

// Never let JSON.stringify silently turn NaN into null, omit undefined keys,
// flatten a Date, or drop sparse array entries from the reviewed snapshot.
export function captureAnswers(
  value: unknown,
): Readonly<Record<string, unknown>> {
  if (!plainObject(value))
    throw new Error("Черновик ответов должен быть JSON-объектом.");
  const active = new WeakSet<object>();
  function copy(input: unknown): unknown {
    if (
      input === null ||
      typeof input === "string" ||
      typeof input === "boolean"
    )
      return input;
    if (typeof input === "number" && Number.isFinite(input)) return input;
    if (typeof input !== "object" || !input)
      throw new Error(
        "Ответ содержит значение, которое нельзя передать в JSON.",
      );
    if (active.has(input))
      throw new Error("Ответ содержит циклическую структуру.");
    if (Object.getOwnPropertySymbols(input).length)
      throw new Error("Ответ содержит неподдерживаемые JSON-поля.");
    active.add(input);
    try {
      if (Array.isArray(input)) {
        if (Object.getOwnPropertyNames(input).length !== input.length + 1)
          throw new Error(
            "Ответ содержит неполный или нестандартный JSON-массив.",
          );
        const result = [];
        for (let i = 0; i < input.length; i++) {
          const descriptor = Object.getOwnPropertyDescriptor(input, String(i));
          if (!descriptor?.enumerable || !("value" in descriptor))
            throw new Error(
              "Ответ содержит неполный или нестандартный JSON-массив.",
            );
          result.push(copy(descriptor.value));
        }
        return Object.freeze(result);
      }
      if (!plainObject(input))
        throw new Error(
          "Ответ содержит значение, которое нельзя передать в JSON.",
        );
      const entries = Object.getOwnPropertyNames(input).map((key) => {
        const descriptor = Object.getOwnPropertyDescriptor(input, key)!;
        if (!descriptor.enumerable || !("value" in descriptor))
          throw new Error("Ответ содержит неподдерживаемые JSON-поля.");
        return [key, copy(descriptor.value)] as const;
      });
      return Object.freeze(Object.fromEntries(entries));
    } finally {
      active.delete(input);
    }
  }
  return copy(value) as Readonly<Record<string, unknown>>;
}

// Presence is distinct from format and correctness. Empty JSON containers are
// present; whether their shape satisfies an item is checked by the server.
export function answerPresent(value: unknown): boolean {
  return (
    value !== undefined &&
    value !== null &&
    (typeof value !== "string" || value.trim().length > 0)
  );
}

export function validateReviewReceipt(value: ReviewReceipt): void {
  if (
    !value ||
    !Number.isInteger(value.answered) ||
    !Number.isInteger(value.total) ||
    value.total < 1 ||
    value.answered < 0 ||
    value.answered > value.total ||
    typeof value.structural_ready !== "boolean" ||
    !Array.isArray(value.issues) ||
    value.issues.some(
      (issue) =>
        !issue ||
        (issue.item_id !== null && typeof issue.item_id !== "string") ||
        !["missing", "format", "limit"].includes(issue.kind) ||
        typeof issue.detail !== "string",
    ) ||
    !Array.isArray(value.limitations) ||
    value.limitations.some((entry) => typeof entry !== "string") ||
    ![
      value.review_token,
      value.public_form_sha256,
      value.saved_answers_sha256,
      value.prospective_answers_sha256,
    ].every(
      (digest) =>
        digest === null || (typeof digest === "string" && sha256.test(digest)),
    )
  )
    throw new Error(
      "Сервер не вернул целую проверку черновика. Повтори проверку.",
    );
}

export function reviewSubmissionAllowed(
  review: CapturedReview | null,
  allowMissing: boolean,
): boolean {
  if (!review) return false;
  try {
    validateReviewReceipt(review.receipt);
  } catch {
    return false;
  }
  const { receipt } = review;
  if (
    ![
      receipt.review_token,
      receipt.public_form_sha256,
      receipt.prospective_answers_sha256,
    ].every((digest) => typeof digest === "string" && sha256.test(digest))
  )
    return false;
  if (receipt.issues.some((issue) => issue.kind !== "missing")) return false;
  if (receipt.issues.some((issue) => issue.item_id === null)) return false;
  const missing = new Set(receipt.issues.map((issue) => issue.item_id)).size;
  if (missing)
    return allowMissing && missing === receipt.total - receipt.answered;
  return receipt.structural_ready && receipt.answered === receipt.total;
}

export function reviewedSubmitBody(
  review: CapturedReview,
  allowMissing: boolean,
) {
  if (!reviewSubmissionAllowed(review, allowMissing))
    throw new Error(
      "Исправь формат ответов или явно подтверди отправку пропусков.",
    );
  return {
    answers: review.answers,
    review_token: review.receipt.review_token,
    allow_incomplete:
      allowMissing &&
      review.receipt.issues.some((issue) => issue.kind === "missing"),
  };
}
