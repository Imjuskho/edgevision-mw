import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { PageShell } from "../components/PageShell";
import { StatCard, Badge, Spinner, EmptyState, ErrorState } from "../components/ui";
import api from "../services/api";

interface CorridorNode {
  node_id: string;
  node_label: string;
  status: string;
  district: string | null;
  category: string | null;
}

interface Corridor {
  corridor_id: string;
  name: string;
  node_count: number;
  nodes: CorridorNode[];
}

interface Invoice {
  id: string;
  invoice_number: string;
  subscription_period_start: string;
  subscription_period_end: string;
  node_count: number;
  total_usd: string;
  total_mwk: string;
  status: string;
  created_at: string;
}

interface Subscription {
  buyer_id: string;
  node_count: number;
  monthly_price_usd: string;
  monthly_price_mwk: string;
  status: string;
  corridors: string[];
}

function subscriptionVariant(status: string): "success" | "warning" | "danger" | "info" {
  switch (status?.toLowerCase()) {
    case "active":
      return "success";
    case "past_due":
    case "suspended":
      return "warning";
    case "cancelled":
      return "danger";
    default:
      return "info";
  }
}

function invoiceVariant(status: string): "success" | "warning" | "danger" | "info" {
  switch (status?.toLowerCase()) {
    case "paid":
      return "success";
    case "pending":
      return "warning";
    case "failed":
      return "danger";
    default:
      return "info";
  }
}

function statusDot(status: string): "success" | "warning" | "danger" | "info" {
  switch (status?.toUpperCase()) {
    case "ONLINE":
      return "success";
    case "DEGRADED":
      return "warning";
    case "OFFLINE":
      return "danger";
    default:
      return "info";
  }
}

export default function BuyerDashboardPage() {
  const { t } = useTranslation();
  const [corridors, setCorridors] = useState<Corridor[]>([]);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.get<Corridor[]>("/buyer/corridors"),
      api.get<Subscription>("/buyer/subscription"),
      api.get<Invoice[]>("/buyer/invoices"),
    ])
      .then(([corrRes, subRes, invRes]) => {
        if (!cancelled) {
          setCorridors(corrRes.data);
          setSubscription(subRes.data);
          setInvoices(invRes.data);
          setError(null);
        }
      })
      .catch((err: { response?: { data?: { detail?: string } } }) => {
        if (!cancelled) setError(err.response?.data?.detail || "Analodha vuto");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [refreshKey]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Spinner />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <ErrorState
          title={t("buyer.loadError", "Analodha vuto")}
          body={error}
          onRetry={() => { setLoading(true); setError(null); setRefreshKey((k) => k + 1); }}
        />
      </div>
    );
  }

  const totalNodes = corridors.reduce((sum, c) => sum + c.node_count, 0);
  const monthlyPrice = subscription ? Number(subscription.monthly_price_usd) : 0;

  return (
    <PageShell
      accent="data"
      title={t("buyer.title", "Chimbale cha Mwini")}
      subtitle={t("buyer.subtitle", "Ma dashboard anu a data marketplace")}
    >
      <div className="settings-grid">
        {/* Stats */}
        <section className="settings-panel">
          <h2>{t("buyer.overview", "Kuwunika")}</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "var(--space-3)" }}>
            <StatCard
              label={t("buyer.totalNodes", "Nodes Zonse")}
              value={totalNodes.toLocaleString()}
            />
            <StatCard
              label={t("buyer.monthlyPrice", "Mtengo Pa Mwezi")}
              value={`$${monthlyPrice.toLocaleString()}`}
            />
            <StatCard
              label={t("buyer.activeCorridors", "Corridors Oyimba")}
              value={corridors.length.toLocaleString()}
            />
          </div>
        </section>

        {/* Corridors */}
        <section className="settings-panel">
          <h2>{t("buyer.corridors", "Ma Corridors")}</h2>
          {corridors.length === 0 ? (
            <EmptyState
              title={t("buyer.noCorridors", "Palibe corridors")}
              body={t("buyer.noCorridorsBody", "Corridors adzaonekera pano.")}
            />
          ) : (
            <div className="settings-toggle-list">
              {corridors.map((corridor) => (
                <div
                  key={corridor.corridor_id}
                  className="settings-toggle-row"
                  style={{ justifyContent: "space-between" }}
                >
                  <div className="settings-toggle-copy">
                    <span className="settings-toggle-label">{corridor.name}</span>
                    <span className="settings-toggle-desc">
                      {corridor.node_count} {t("buyer.nodes", "nodes")}
                    </span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                    {corridor.nodes.slice(0, 3).map((node) => (
                      <Badge key={node.node_id} variant={statusDot(node.status)}>
                        {node.node_label}
                      </Badge>
                    ))}
                    {corridor.nodes.length > 3 && (
                      <Badge variant="info">
                        +{corridor.nodes.length - 3}
                      </Badge>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Subscription */}
        <section className="settings-panel">
          <h2>{t("buyer.subscription", "Kulembetsa")}</h2>
          {!subscription ? (
            <EmptyState
              title={t("buyer.noSubscription", "Palibe kulembetsa")}
              body={t("buyer.noSubscriptionBody", "Kulembetsa kudzaonekera pano.")}
            />
          ) : (
            <div className="settings-toggle-list">
              <div className="settings-toggle-row" style={{ justifyContent: "space-between" }}>
                <div className="settings-toggle-copy">
                  <span className="settings-toggle-label">{t("buyer.status", "Status")}</span>
                  <span className="settings-toggle-desc">
                    {subscription.status === "active"
                      ? t("buyer.active", "Yoyimba")
                      : subscription.status}
                  </span>
                </div>
                <Badge variant={subscriptionVariant(subscription.status)}>
                  {subscription.status}
                </Badge>
              </div>
              <div className="settings-toggle-row" style={{ justifyContent: "space-between" }}>
                <div className="settings-toggle-copy">
                  <span className="settings-toggle-label">{t("buyer.nodeCount", "Chiwerengero cha Nodes")}</span>
                  <span className="settings-toggle-desc">
                    {subscription.node_count} {t("buyer.nodes", "nodes")}
                  </span>
                </div>
              </div>
              <div className="settings-toggle-row" style={{ justifyContent: "space-between" }}>
                <div className="settings-toggle-copy">
                  <span className="settings-toggle-label">{t("buyer.monthlyCost", "Mtengo Pa Mwezi")}</span>
                  <span className="settings-toggle-desc">
                    ${Number(subscription.monthly_price_usd).toLocaleString()} USD
                  </span>
                </div>
              </div>
            </div>
          )}
        </section>

        {/* Invoices */}
        <section className="settings-panel">
          <h2>{t("buyer.invoices", "Mauliro")}</h2>
          {invoices.length === 0 ? (
            <EmptyState
              title={t("buyer.noInvoices", "Palibe mauliro")}
              body={t("buyer.noInvoicesBody", "Mauliro adzaonekera pano.")}
            />
          ) : (
            <div className="settings-toggle-list">
              {invoices.map((inv) => (
                <div
                  key={inv.id}
                  className="settings-toggle-row"
                  style={{ justifyContent: "space-between" }}
                >
                  <div className="settings-toggle-copy">
                    <span className="settings-toggle-label">{inv.invoice_number}</span>
                    <span className="settings-toggle-desc">
                      {new Date(inv.subscription_period_start).toLocaleDateString()} —{" "}
                      {new Date(inv.subscription_period_end).toLocaleDateString()}
                    </span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                    <span className="settings-toggle-label">
                      ${Number(inv.total_usd).toLocaleString()}
                    </span>
                    <Badge variant={invoiceVariant(inv.status)}>
                      {inv.status}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* License Options */}
        <section className="settings-panel">
          <h2>{t("buyer.licenseOptions", "License Options")}</h2>
          <p style={{ marginBottom: "var(--space-3)", fontSize: "var(--font-size-sm)", color: "var(--text-muted)" }}>
            {t("buyer.licenseOptionsDesc", "Available licensing models for dataset purchases. Pricing multipliers apply to the base dataset price.")}
          </p>
          <div className="settings-toggle-list">
            {[
              { type: "ONE_TIME", multiplier: "0.5x", desc: t("buyer.oneTimeDesc", "Single-use license for one project. Lowest cost option."), variant: "info" as const },
              { type: "ANNUAL", multiplier: "1.0x", desc: t("buyer.annualDesc", "12-month renewable license. Standard pricing."), variant: "success" as const },
              { type: "PERPETUAL", multiplier: "1.5x", desc: t("buyer.perpetualDesc", "Lifetime license with no expiration. 50% premium."), variant: "info" as const },
              { type: "EXCLUSIVE", multiplier: "2.5x", desc: t("buyer.exclusiveDesc", "Exclusive rights — no other buyer can access. 150% premium."), variant: "warning" as const },
              { type: "COMMISSIONED", multiplier: "3.0x", desc: t("buyer.commissionedDesc", "Bespoke data collection to your specifications. 200% premium."), variant: "danger" as const },
            ].map((lic) => (
              <div
                key={lic.type}
                className="settings-toggle-row"
                style={{ justifyContent: "space-between" }}
              >
                <div className="settings-toggle-copy">
                  <span className="settings-toggle-label">{lic.type}</span>
                  <span className="settings-toggle-desc">{lic.desc}</span>
                </div>
                <Badge variant={lic.variant}>{lic.multiplier}</Badge>
              </div>
            ))}
          </div>
        </section>
      </div>
    </PageShell>
  );
}
