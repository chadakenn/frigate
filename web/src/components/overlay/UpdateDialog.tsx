import { useEffect, useState } from "react";
import axios from "axios";
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
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    const refresh = () => {
      axios.get<Status>("updater/status")
        .then((response) => { setStatus(response.data); setError(""); })
        .catch(() => setError("Host updater unavailable"));
    };
    refresh();
    const timer = window.setInterval(refresh, 3000);
    return () => window.clearInterval(timer);
  }, [open]);

  const start = async () => {
    try {
      await axios.post("updater/start");
      setStatus({ phase: "pulling", message: "Downloading the update" });
    } catch {
      setError("Unable to start the update. Check host updater logs.");
    }
  };

  const busy = ["pulling", "installing", "rollback"].includes(status?.phase ?? "");
  const available = status?.available;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Update Frigate</DialogTitle>
          <DialogDescription>Running {current}. Latest upstream release: {latest}.</DialogDescription>
        </DialogHeader>
        <p role="status">{error || status?.message || "Checking for a custom image..."}</p>
        {available && available !== current && !busy && (
          <Button onClick={start}>Install {available}</Button>
        )}
        {busy && <p>The updater will continue while Frigate restarts. Reopen this page shortly.</p>}
      </DialogContent>
    </Dialog>
  );
}
