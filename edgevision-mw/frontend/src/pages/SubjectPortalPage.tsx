import { useState } from "react";
import { useTranslation } from "react-i18next";
import { PageShell } from "../components/PageShell";
import {
  StatCard,
  Badge,
  Button,
  Spinner,
  EmptyState,
  ErrorState,
  Input,
} from "../components/ui";
import api from "../services/api";

interface SubjectLookup {
  subject_hash: string;
  token: string;
  total_rewards_mwk: number;
  exists: boolean;
}

interface ConsentRecord {
  tx_hash: string;
  subject_hash: string;
  purposes: string[];
  status: string;
  recorded_at: string;
}

interface SubjectHistory {
  subject_hash: string;
  records: ConsentRecord[];
  total_count: number;
  opted_out: boolean;
}

interface SubjectRewards {
  subject_hash: string;
  total_mwk: number;
  withdrawn_mwk: number;
  pending_mwk: number;
}

function consentVariant(s: string): "success" | "warning" | "danger" {
  switch (s?.toLowerCase()) {
    case "active":
      return "success";
    case "withdrawn":
      return "danger";
    case "expired":
      return "warning";
    default:
      return "warning";
  }
}

function consentLabel(s: string, t: (key: string, fallback: string) => string): string {
  switch (s?.toLowerCase()) {
    case "active":
      return t("subject.consentActive", "Active");
    case "withdrawn":
      return t("subject.consentWithdrawn", "Withdrawn");
    case "expired":
      return t("subject.consentExpired", "Expired");
    default:
      return s;
  }
}

export default function SubjectPortalPage() {
  const { t } = useTranslation();

  const [hashInput, setHashInput] = useState("");
  const [activeHash, setActiveHash] = useState<string | null>(null);

  const [lookup, setLookup] = useState<SubjectLookup | null>(null);
  const [history, setHistory] = useState<SubjectHistory | null>(null);
  const [rewards, setRewards] = useState<SubjectRewards | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [withdrawing, setWithdrawing] = useState(false);
  const [withdrawSuccess, setWithdrawSuccess] = useState(false);

  const handleSearch = async () => {
    const trimmed = hashInput.trim();
    if (!trimmed) return;

    setLoading(true);
    setError(null);
    setLookup(null);
    setHistory(null);
    setRewards(null);
    setWithdrawSuccess(false);
    setActiveHash(null);

    try {
      const lookupRes = await api.get<SubjectLookup>("/subject/lookup", {
        params: { hash: trimmed },
      });
      const lookupData = lookupRes.data;

      if (!lookupData.exists) {
        setError(t("subject.notFound", "Dzinali silinapezeke"));
        setLoading(false);
        return;
      }

      setLookup(lookupData);
      setActiveHash(lookupData.subject_hash);

      const [historyRes, rewardsRes] = await Promise.all([
        api.get<SubjectHistory>(`/subject/${lookupData.subject_hash}/history`),
        api.get<SubjectRewards>(`/subject/${lookupData.subject_hash}/rewards`),
      ]);

      setHistory(historyRes.data);
      setRewards(rewardsRes.data);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail || t("subject.lookupError", "Analodha vuto lomasulira");
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleWithdraw = async () => {
    if (!activeHash || withdrawing) return;
    setWithdrawing(true);
    setWithdrawSuccess(false);

    try {
      await api.post(`/subject/${activeHash}/withdraw`, {
        purpose: "privacy",
      });

      setWithdrawSuccess(true);

      const historyRes = await api.get<SubjectHistory>(
        `/subject/${activeHash}/history`,
      );
      setHistory(historyRes.data);

      const rewardsRes = await api.get<SubjectRewards>(
        `/subject/${activeHash}/rewards`,
      );
      setRewards(rewardsRes.data);
    } catch {
      setError(t("subject.withdrawError", "Kusiyana chilolezo sikunachitike"));
    } finally {
      setWithdrawing(false);
    }
  };

  const isWithdrawn =
    history?.opted_out ||
    history?.records.some(
      (r) => r.status.toLowerCase() === "withdrawn",
    ) ||
    lookup === null;

  return (
    <PageShell
      accent="quality"
      title={t("subject.title", "Tsamba la Yemwe")}
      subtitle={t(
        "subject.subtitle",
        "Yang'anirani chilolezo ndi zipindulo zanu",
      )}
    >
      <div className="settings-grid">
        {/* Lookup Panel */}
        <section className="settings-panel">
          <h2>
            {t("subject.lookup", "Sakani Dzina")}
          </h2>
          <div
            style={{
              display: "flex",
              gap: "var(--space-2)",
              alignItems: "center",
            }}
          >
            <Input
              type="text"
              placeholder={t(
                "subject.hashPlaceholder",
                "Lowetsani subject hash...",
              )}
              value={hashInput}
              onChange={(e) => setHashInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSearch();
              }}
            />
            <Button
              variant="primary"
              onClick={handleSearch}
              loading={loading}
            >
              {t("subject.search", "Sakani")}
            </Button>
          </div>
        </section>

        {/* Loading */}
        {loading && (
          <div
            style={{
              display: "flex",
              justifyContent: "center",
              padding: "var(--space-6)",
            }}
          >
            <Spinner />
          </div>
        )}

        {/* Error */}
        {error && !loading && (
          <ErrorState
            title={t("subject.error", "Vuto")}
            body={error}
            onRetry={handleSearch}
            retryLabel={t("subject.retry", "Yesetsani Kachiwiri")}
          />
        )}

        {/* Empty State */}
        {!loading && !error && !lookup && (
          <EmptyState
            title={t(
              "subject.emptyTitle",
              "Lowetsani subject hash kuti muwone zambiri",
            )}
            body={t(
              "subject.emptyBody",
              "Gwiritsani ntchito fomu pamwambapa kufunsa chilolezo ndi zipindulo.",
            )}
          />
        )}

        {/* Subject Details */}
        {lookup && !loading && (
          <>
            {/* Stats Row */}
            <section className="settings-panel">
              <h2>
                {t("subject.details", "Zambiri za Dzina")}
              </h2>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns:
                    "repeat(auto-fit, minmax(160px, 1fr))",
                  gap: "var(--space-3)",
                }}
              >
                <StatCard
                  label={t("subject.hash", "Subject Hash")}
                  value={`${lookup.subject_hash.slice(0, 12)}...`}
                />
                <StatCard
                  label={t(
                    "subject.totalRewards",
                    "Zipindulo Zonse",
                  )}
                  value={`MWK ${lookup.total_rewards_mwk.toLocaleString()}`}
                />
                <StatCard
                  label={t(
                    "subject.consentRecords",
                    "Makalata a Chilolezo",
                  )}
                  value={history?.total_count?.toLocaleString() ?? "0"}
                />
              </div>
            </section>

            {/* Consent History */}
            <section className="settings-panel">
              <h2>
                {t("subject.history", "Makalata a Chilolezo")}
              </h2>
              {!history || history.records.length === 0 ? (
                <EmptyState
                  title={t(
                    "subject.noHistory",
                    "Palibe makalata a chilolezo",
                  )}
                  body={t(
                    "subject.noHistoryBody",
                    "Dzina ili silinazo makalata.",
                  )}
                />
              ) : (
                <div className="settings-toggle-list">
                  {history.records.map((record) => (
                    <div
                      key={record.tx_hash}
                      className="settings-toggle-row"
                      style={{
                        justifyContent: "space-between",
                      }}
                    >
                      <div className="settings-toggle-copy">
                        <span className="settings-toggle-label">
                          {record.purposes.length > 0
                            ? record.purposes.join(", ")
                            : t(
                                "subject.noPurposes",
                                "Palibe zolinga",
                              )}
                        </span>
                        <span className="settings-toggle-desc">
                          {new Date(
                            record.recorded_at,
                          ).toLocaleDateString()}
                        </span>
                      </div>
                      <Badge variant={consentVariant(record.status)}>
                        {consentLabel(record.status, t)}
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* Rewards Panel */}
            {rewards && (
              <section className="settings-panel">
                <h2>
                  {t("subject.rewards", "Zipindulo")}
                </h2>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns:
                      "repeat(auto-fit, minmax(140px, 1fr))",
                    gap: "var(--space-3)",
                  }}
                >
                  <StatCard
                    label={t("subject.totalMwk", "Zonse")}
                    value={`MWK ${rewards.total_mwk.toLocaleString()}`}
                  />
                  <StatCard
                    label={t(
                      "subject.withdrawnMwk",
                      "Zatengedwa",
                    )}
                    value={`MWK ${rewards.withdrawn_mwk.toLocaleString()}`}
                  />
                  <StatCard
                    label={t("subject.pendingMwk", "Zodikirira")}
                    value={`MWK ${rewards.pending_mwk.toLocaleString()}`}
                  />
                </div>
              </section>
            )}

            {/* Withdraw Panel */}
            <section className="settings-panel">
              <h2>
                {t("subject.withdrawTitle", "Chotsani Chilolezo")}
              </h2>
              <p
                style={{
                  fontSize: "var(--text-sm)",
                  color: "var(--text-muted)",
                  marginBottom: "var(--space-3)",
                }}
              >
                {t(
                  "subject.withdrawDesc",
                  "Muli ufulu wosiya chilolezo nthawi zilizonse. Zikwizikizo zanu zidzasiya.",
                )}
              </p>
              {withdrawSuccess && (
                <p
                  style={{
                    fontSize: "var(--text-sm)",
                    color: "var(--color-success, #34d399)",
                    marginBottom: "var(--space-3)",
                  }}
                >
                  {t(
                    "subject.withdrawSuccess",
                    "Chilolezo chasiyidwa bwino.",
                  )}
                </p>
              )}
              <Button
                variant="danger"
                loading={withdrawing}
                disabled={
                  isWithdrawn ||
                  history?.opted_out
                }
                onClick={handleWithdraw}
              >
                {withdrawing
                  ? t("subject.withdrawing", "Kusiyana...")
                  : isWithdrawn
                    ? t(
                        "subject.alreadyWithdrawn",
                        "Yasiyidwa kale",
                      )
                    : t(
                        "subject.withdraw",
                        "Chotsani Chilolezo",
                      )}
              </Button>
            </section>
          </>
        )}
      </div>
    </PageShell>
  );
}
