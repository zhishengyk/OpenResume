import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Filter, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useState } from "react";
import { api } from "../lib/api";

const VARIANT_LABELS: Record<string, string> = {
  experienced: "社招",
  campus: "校招",
  internship: "实习",
};

interface SearchFilterSidebarProps {
  selectedVariants: string[];
  selectedCompanies: string[];
  onVariantsChange: (variants: string[]) => void;
  onCompaniesChange: (companies: string[]) => void;
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
}

function SectionToggle({
  title,
  count,
  expanded,
  onToggle,
}: {
  title: string;
  count: number;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="flex w-full items-center justify-between rounded-2xl px-3 py-2 text-left transition hover:bg-paper"
    >
      <span className="text-xs uppercase tracking-[0.2em] text-slate">{title}</span>
      <span className="inline-flex items-center gap-2 text-sm font-medium text-ink">
        <span className="rounded-full bg-paper px-2 py-0.5 text-xs text-slate">{count}</span>
        {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
      </span>
    </button>
  );
}

export function SearchFilterSidebar({
  selectedVariants,
  selectedCompanies,
  onVariantsChange,
  onCompaniesChange,
  collapsed,
  onCollapsedChange,
}: SearchFilterSidebarProps) {
  const [variantsExpanded, setVariantsExpanded] = useState(true);
  const [companiesExpanded, setCompaniesExpanded] = useState(true);

  const variantsQuery = useQuery({
    queryKey: ["source-variants"],
    queryFn: api.getSourceVariants,
  });

  const companiesQuery = useQuery({
    queryKey: ["source-companies"],
    queryFn: api.getSourceCompanies,
  });

  const variants = variantsQuery.data || [];
  const companies = companiesQuery.data || [];

  const handleVariantToggle = (variant: string) => {
    if (selectedVariants.includes(variant)) {
      onVariantsChange(selectedVariants.filter((v) => v !== variant));
    } else {
      onVariantsChange([...selectedVariants, variant]);
    }
  };

  const handleCompanyToggle = (company: string) => {
    if (selectedCompanies.includes(company)) {
      onCompaniesChange(selectedCompanies.filter((c) => c !== company));
    } else {
      onCompaniesChange([...selectedCompanies, company]);
    }
  };

  if (collapsed) {
    return (
      <aside className="rounded-[28px] border border-ink/10 bg-shell/90 p-4 shadow-console xl:sticky xl:top-4">
        <button
          type="button"
          onClick={() => onCollapsedChange(false)}
          className="inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-ink/10 bg-paper px-3 py-2 text-sm font-medium text-ink transition hover:border-ink/20"
          aria-label="展开筛选"
        >
          <PanelLeftOpen size={16} />
          <span className="xl:hidden">展开筛选</span>
        </button>
        <div className="mt-4 space-y-2 text-xs text-slate">
          <p className="flex items-center justify-between rounded-xl bg-paper px-3 py-2">
            <span>招聘类型</span>
            <span>{selectedVariants.length}</span>
          </p>
          <p className="flex items-center justify-between rounded-xl bg-paper px-3 py-2">
            <span>公司</span>
            <span>{selectedCompanies.length}</span>
          </p>
        </div>
      </aside>
    );
  }

  return (
    <aside className="rounded-[28px] border border-ink/10 bg-shell/90 p-5 shadow-console xl:sticky xl:top-4">
      <div className="flex items-center justify-between">
        <p className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.24em] text-slate">
          <Filter size={14} />
          来源筛选
        </p>
        <button
          type="button"
          onClick={() => onCollapsedChange(true)}
          className="inline-flex items-center gap-2 rounded-xl border border-ink/10 bg-paper px-3 py-1.5 text-xs font-medium text-ink transition hover:border-ink/20"
        >
          <PanelLeftClose size={14} />
          折叠
        </button>
      </div>

      <div className="mt-4 space-y-4">
        <section className="rounded-2xl border border-ink/10 bg-shell p-2">
          <SectionToggle
            title="招聘类型"
            count={selectedVariants.length}
            expanded={variantsExpanded}
            onToggle={() => setVariantsExpanded((v) => !v)}
          />
          {variantsExpanded ? (
            <div className="space-y-2 px-2 pb-2">
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => onVariantsChange([...variants])}
                  className="rounded-lg px-2 py-1 text-xs text-slate transition hover:bg-paper hover:text-ink"
                >
                  全选
                </button>
                <button
                  type="button"
                  onClick={() => onVariantsChange([])}
                  className="rounded-lg px-2 py-1 text-xs text-slate transition hover:bg-paper hover:text-ink"
                >
                  清空
                </button>
              </div>
              {variants.map((variant) => {
                const checked = selectedVariants.includes(variant);
                const label = VARIANT_LABELS[variant] || variant;
                return (
                  <label
                    key={variant}
                    className={`flex cursor-pointer items-center gap-3 rounded-xl border px-3 py-2 text-sm transition ${
                      checked
                        ? "border-ink/30 bg-ink text-shell"
                        : "border-ink/10 bg-paper text-ink hover:border-ink/20"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => handleVariantToggle(variant)}
                      className="mt-0.5"
                    />
                    <span>{label}</span>
                  </label>
                );
              })}
              {selectedVariants.length === 0 ? (
                <p className="text-xs text-slate">未选择时将搜索全部招聘类型</p>
              ) : null}
            </div>
          ) : null}
        </section>

        <section className="rounded-2xl border border-ink/10 bg-shell p-2">
          <SectionToggle
            title="公司"
            count={selectedCompanies.length}
            expanded={companiesExpanded}
            onToggle={() => setCompaniesExpanded((v) => !v)}
          />
          {companiesExpanded ? (
            <div className="space-y-2 px-2 pb-2">
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => onCompaniesChange([...companies])}
                  className="rounded-lg px-2 py-1 text-xs text-slate transition hover:bg-paper hover:text-ink"
                >
                  全选
                </button>
                <button
                  type="button"
                  onClick={() => onCompaniesChange([])}
                  className="rounded-lg px-2 py-1 text-xs text-slate transition hover:bg-paper hover:text-ink"
                >
                  清空
                </button>
              </div>
              {companies.map((company) => {
                const checked = selectedCompanies.includes(company);
                return (
                  <label
                    key={company}
                    className={`flex cursor-pointer items-center gap-3 rounded-xl border px-3 py-2 text-sm transition ${
                      checked
                        ? "border-ink/30 bg-ink text-shell"
                        : "border-ink/10 bg-paper text-ink hover:border-ink/20"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => handleCompanyToggle(company)}
                      className="mt-0.5"
                    />
                    <span>{company}</span>
                  </label>
                );
              })}
              {selectedCompanies.length === 0 ? (
                <p className="text-xs text-slate">未选择时将搜索全部公司</p>
              ) : null}
            </div>
          ) : null}
        </section>
      </div>
    </aside>
  );
}
