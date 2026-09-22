import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { studioApi } from "../services/api";
import { Button, EmptyState, ErrorState } from "../components/ui";
import { DatasetPreviewModal } from "../components/DatasetPreviewModal";

interface MarketplaceDataset {
  id: string;
  dataset_id: string;
  name: string;
  sample_count: number;
  classes: Record<string, number>;
  price_usd: number | string;
  license_type: string;
  iaa_score: number;
  consent_coverage_pct: number;
  status: string;
  created_at: string;
}

const LICENSE_OPTIONS = ["", "PERPETUAL", "ANNUAL", "EXCLUSIVE"] as const;
const CATEGORY_OPTIONS = ["", "ROAD", "AGRI", "WILDLIFE", "DOC", "BIOMETRIC"] as const;

export default function MarketplacePage() {
  const { t } = useTranslation();
  const [datasets, setDatasets] = useState<MarketplaceDataset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [search, setSearch] = useState("");
  const [licenseFilter, setLicenseFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [quoteDatasetId, setQuoteDatasetId] = useState<string | null>(null);
  const [quoteLoading, setQuoteLoading] = useState(false);
  const [quoteResult, setQuoteResult] = useState<string | null>(null);
  const [previewDataset, setPreviewDataset] = useState<MarketplaceDataset | null>(null);

  const loadDatasets = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const params: Record<string, string | number> = { page_size: 50 };
      if (search) params.search = search;
      if (licenseFilter) params.license_type = licenseFilter;
      const resp = await studioApi.listDatasets(params);
      const items = resp.data?.items || resp.data;
      let list: MarketplaceDataset[] = Array.isArray(items) ? items : [];
      if (categoryFilter) {
        list = list.filter((ds) => {
          const classKeys = Object.keys(ds.classes || {});
          return classKeys.some((k) => k.toUpperCase().includes(categoryFilter.toUpperCase()));
        });
      }
      setDatasets(list);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [search, licenseFilter, categoryFilter]);

  useEffect(() => {
    void loadDatasets();
  }, [loadDatasets]);

  const handleRequestQuote = async (datasetId: string) => {
    setQuoteDatasetId(datasetId);
    setQuoteLoading(true);
    setQuoteResult(null);
    try {
      const resp = await studioApi.requestQuote(datasetId, "ANNUAL", "MW");
      const data = resp.data;
      setQuoteResult(
        t(
          "marketplace.quoteResult",
          "Quote: ${{price}} (expires {{date}})",
          {
            price: Number(data.total_price_usd).toFixed(2),
            date: new Date(data.expires_at).toLocaleDateString(),
          },
        ),
      );
    } catch {
      setQuoteResult(t("marketplace.quoteFailed", "Could not generate quote. Please try again."));
    } finally {
      setQuoteLoading(false);
      setQuoteDatasetId(null);
    }
  };

  const classCount = (classes: Record<string, number>) => Object.keys(classes).length;

  return (
    <div className="page-shell marketplace-page">
      <header className="marketplace-header">
        <h1>{t("marketplace.title", "Dataset Marketplace")}</h1>
        <p className="text-secondary">{t("marketplace.subtitle", "Browse and license certified datasets from Malawi field captures.")}</p>
      </header>

      <div className="marketplace-filters">
        <input
          type="search"
          className="marketplace-search"
          placeholder={t("marketplace.search", "Search datasets")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label={t("marketplace.search", "Search datasets")}
        />
        <select
          className="marketplace-filter-select"
          value={licenseFilter}
          onChange={(e) => setLicenseFilter(e.target.value)}
          aria-label={t("marketplace.filterLicense", "Filter by license")}
        >
          <option value="">{t("marketplace.allLicenses", "All licenses")}</option>
          {LICENSE_OPTIONS.filter(Boolean).map((opt) => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
        <select
          className="marketplace-filter-select"
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          aria-label={t("marketplace.filterCategory", "Filter by category")}
        >
          <option value="">{t("marketplace.allCategories", "All categories")}</option>
          {CATEGORY_OPTIONS.filter(Boolean).map((opt) => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      </div>

      {loading && <p className="empty-state">{t("common.loading", "Loading...")}</p>}
      {error && (
        <ErrorState
          title={t("marketplace.loadFailed", "Could not load datasets")}
          body={t("marketplace.loadFailedBody", "Check your connection and try again.")}
          onRetry={() => void loadDatasets()}
          retryLabel={t("datasets.retry", "Retry")}
        />
      )}

      {!loading && !error && datasets.length === 0 && (
        <EmptyState
          title={t("marketplace.noResults", "No datasets found")}
          body={t("marketplace.noResultsBody", "Try adjusting your search or filters.")}
        />
      )}

      {!loading && !error && datasets.length > 0 && (
        <>
          <p className="marketplace-count">
            {t("marketplace.found", "{{count}} datasets available", { count: datasets.length })}
          </p>
          <div className="marketplace-grid">
            {datasets.map((ds) => (
              <div key={ds.dataset_id} className="marketplace-card">
                <div className="marketplace-card-header">
                  <h3 className="marketplace-card-title">{ds.name || ds.dataset_id}</h3>
                  <span className="marketplace-status-chip">{ds.status}</span>
                </div>
                <div className="marketplace-card-stats">
                  <span>{t("marketplace.samples", "{{count}} samples", { count: ds.sample_count })}</span>
                  <span>{t("marketplace.classes", "{{count}} classes", { count: classCount(ds.classes) })}</span>
                </div>
                <div className="marketplace-card-meta">
                  <span>{t("marketplace.price", "From ${{price}}", { price: Number(ds.price_usd).toFixed(2) })}</span>
                  <span>{ds.license_type}</span>
                </div>
                <div className="marketplace-card-scores">
                  {ds.iaa_score > 0 && (
                    <span className="marketplace-score marketplace-score--iaa">
                      {t("marketplace.iaaScore", "IAA {{score}}%", { score: (ds.iaa_score * 100).toFixed(0) })}
                    </span>
                  )}
                  {ds.consent_coverage_pct > 0 && (
                    <span className="marketplace-score marketplace-score--consent">
                      {t("marketplace.consentCoverage", "{{pct}}% consent", { pct: ds.consent_coverage_pct.toFixed(0) })}
                    </span>
                  )}
                </div>
                <div className="marketplace-card-actions">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setPreviewDataset(ds)}
                  >
                    {t("marketplace.preview", "Preview")}
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => void handleRequestQuote(ds.dataset_id)}
                    disabled={quoteLoading && quoteDatasetId === ds.dataset_id}
                  >
                    {quoteLoading && quoteDatasetId === ds.dataset_id
                      ? t("marketplace.quoting", "Quoting...")
                      : t("marketplace.requestQuote", "Request Quote")}
                  </Button>
                </div>
              </div>
            ))}
          </div>
          {quoteResult && (
            <div className="marketplace-quote-result" role="status">
              {quoteResult}
            </div>
          )}
        </>
      )}
      {previewDataset && (
        <DatasetPreviewModal dataset={previewDataset} onClose={() => setPreviewDataset(null)} />
      )}
    </div>
  );
}
