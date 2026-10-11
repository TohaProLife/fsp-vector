"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, FlaskConical } from "lucide-react";
import { post, type Attempt } from "@/lib/api";
import { needStartBody } from "@/lib/assessment-scope";
import { Button, ErrorBox, Modal, Notice } from "@/components/ui";

export function NeedPracticeStart({
  invitationId,
  vacancyId,
}: {
  invitationId?: string;
  vacancyId?: string;
}) {
  const router = useRouter();
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  return (
    <>
      <Button
        variant="secondary"
        onClick={() => {
          setError(undefined);
          setConfirm(true);
        }}
      >
        <FlaskConical size={14} /> Практика по потребности
      </Button>
      {confirm && (
        <Modal
          title="Начать практику для этой команды?"
          description="Задания составлены по структурированной потребности компании."
          onClose={() => {
            if (!busy) setConfirm(false);
          }}
        >
          <div className="v-dialog-content">
            <Notice>
              Это отдельное наблюдение по ограниченному набору навыков.
              Глобальная категория и грейд не меняются. Начало практики само по
              себе не открывает твои контакты.
            </Notice>
            <dl className="linear-properties top-gap v-property-list">
              <div className="linear-property-row v-property-row">
                <dt>Попытка</dt>
                <dd>Серверный таймер и сохранение ответов</dd>
              </div>
              <div className="linear-property-row v-property-row">
                <dt>Результат</dt>
                <dd>В собственной истории и у соответствующей компании</dd>
              </div>
              <div className="linear-property-row v-property-row">
                <dt>Повтор</dt>
                <dd>Через 24 часа после завершения</dd>
              </div>
            </dl>
            {error !== undefined && <ErrorBox error={error} />}
            <div className="modal-actions v-form-actions">
              <Button
                variant="secondary"
                disabled={busy}
                onClick={() => setConfirm(false)}
              >
                Вернуться
              </Button>
              <Button
                busy={busy}
                onClick={async () => {
                  setBusy(true);
                  setError(undefined);
                  try {
                    const attempt = await post<Attempt>(
                      "/assessments/need-start",
                      needStartBody({ invitationId, vacancyId }),
                    );
                    if (!attempt.id)
                      throw new Error("Сервер не вернул сохранённую попытку.");
                    router.push(`/assessment/${attempt.id}`);
                  } catch (e) {
                    setError(e);
                    setBusy(false);
                  }
                }}
              >
                Начать практику <ArrowRight size={15} />
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
