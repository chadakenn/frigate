import { useEffect, useState } from "react";
import axios from "axios";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type Status = { phase: string; message: string; available?: string };

export default function UpdateDialog({
  open,
  onOpenChange,
  current,
  latest,
}: {
  open: boolean;
  onOpenChange: (value: boolean) => void;
  current: string;
  latest: string;
}) {
  const { t } = useTranslation("views/system");
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    const refresh = () => {
      axios
        .get<Status>("updater/status")
        .then((response) => {
          setStatus(response.data);
          setError("");
        })
        .catch(() => setError(t("update.unavailable")));
    };
    refresh();
    const timer = window.setInterval(refresh, 3000);
    return () => window.clearInterval(timer);
  }, [open, t]);

  const start = async () => {
    try {
      await axios.post("updater/start");
      setStatus({ phase: "pulling", message: t("update.downloading") });
    } catch {
      setError(t("update.startError"));
    }
  };

  const busy = ["pulling", "installing", "rollback"].includes(
    status?.phase ?? "",
  );
  const available = status?.available;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("update.title")}</DialogTitle>
          <DialogDescription>
            {t("update.description", { current, latest })}
          </DialogDescription>
        </DialogHeader>
        <p role="status">{error || status?.message || t("update.checking")}</p>
        {available && available !== current && !busy && (
          <Button onClick={start}>
            {t("update.install", { version: available })}
          </Button>
        )}
        {busy && <p>{t("update.restarting")}</p>}
      </DialogContent>
    </Dialog>
  );
}
