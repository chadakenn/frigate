import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const DOCKER_UPDATE_COMMANDS = `docker compose pull
docker compose up -d`;
const UPDATE_DOCS_URL = "https://docs.frigate.video/frigate/updating/";

type UpdateAvailableDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentVersion: string;
  latestVersion: string;
};

export default function UpdateAvailableDialog({
  open,
  onOpenChange,
  currentVersion,
  latestVersion,
}: UpdateAvailableDialogProps) {
  const { t } = useTranslation(["views/system", "common"]);
  const releaseUrl = `https://github.com/blakeblackshear/frigate/releases/tag/v${latestVersion}`;

  const copyCommands = async () => {
    try {
      await navigator.clipboard.writeText(DOCKER_UPDATE_COMMANDS);
      toast.success(t("update.copySuccess"));
    } catch {
      toast.error(t("update.copyError"));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("update.title", { version: latestVersion })}</DialogTitle>
          <DialogDescription>
            {t("update.description", {
              current: currentVersion,
              latest: latestVersion,
            })}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 text-sm">
          <p>{t("update.dockerHint")}</p>
          <pre className="overflow-x-auto rounded-md bg-background_alt p-3 font-mono text-xs">
            {DOCKER_UPDATE_COMMANDS}
          </pre>
          <p className="text-muted-foreground">{t("update.haHint")}</p>
        </div>
        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
          <Button variant="outline" size="sm" onClick={copyCommands}>
            {t("update.copyCommands")}
          </Button>
          <Button variant="outline" size="sm" asChild>
            <a href={UPDATE_DOCS_URL} target="_blank" rel="noreferrer">
              {t("update.docs")}
            </a>
          </Button>
          <Button variant="select" size="sm" asChild>
            <a href={releaseUrl} target="_blank" rel="noreferrer">
              {t("update.releaseNotes")}
            </a>
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
