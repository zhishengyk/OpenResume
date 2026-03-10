import { useQuery } from "@tanstack/react-query";
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
}

export function SearchFilterSidebar({
  selectedVariants,
  selectedCompanies,
  onVariantsChange,
  onCompaniesChange,
}: SearchFilterSidebarProps) {
  const variantsQuery = useQuery({
    queryKey: ["source-variants"],
    queryFn: api.getSourceVariants,
  });

  const companiesQuery = useQuery({
    queryKey: ["source-companies"],
    queryFn: api.getSourceCompanies,
  });

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

  const handleSelectAllVariants = () => {
    if (variantsQuery.data) {
      onVariantsChange([...variantsQuery.data]);
    }
  };

  const handleClearVariants = () => {
    onVariantsChange([]);
  };

  const handleSelectAllCompanies = () => {
    if (companiesQuery.data) {
      onCompaniesChange([...companiesQuery.data]);
    }
  };

  const handleClearCompanies = () => {
    onCompaniesChange([]);
  };

  return (
    <aside className="space-y-6">
      <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
        <div className="flex items-center justify-between">
          <p className="text-xs uppercase tracking-[0.24em] text-slate">
            招聘类型
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleSelectAllVariants}
              className="rounded-lg px-2 py-1 text-xs text-slate hover:bg-paper hover:text-ink"
            >
              全选
            </button>
            <button
              type="button"
              onClick={handleClearVariants}
              className="rounded-lg px-2 py-1 text-xs text-slate hover:bg-paper hover:text-ink"
            >
              清空
            </button>
          </div>
        </div>
        <div className="mt-4 space-y-2">
          {variantsQuery.data?.map((variant) => {
            const checked = selectedVariants.includes(variant);
            const label = VARIANT_LABELS[variant] || variant;
            return (
              <label
                key={variant}
                className={`flex cursor-pointer items-center gap-3 rounded-2xl border px-4 py-3 transition ${
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
                <span className="text-sm font-medium">{label}</span>
              </label>
            );
          })}
        </div>
        {selectedVariants.length === 0 && (
          <p className="mt-3 text-xs text-slate">
            未选择时将搜索所有类型
          </p>
        )}
      </section>

      <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
        <div className="flex items-center justify-between">
          <p className="text-xs uppercase tracking-[0.24em] text-slate">
            搜索公司
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleSelectAllCompanies}
              className="rounded-lg px-2 py-1 text-xs text-slate hover:bg-paper hover:text-ink"
            >
              全选
            </button>
            <button
              type="button"
              onClick={handleClearCompanies}
              className="rounded-lg px-2 py-1 text-xs text-slate hover:bg-paper hover:text-ink"
            >
              清空
            </button>
          </div>
        </div>
        <div className="mt-4 space-y-2">
          {companiesQuery.data?.map((company) => {
            const checked = selectedCompanies.includes(company);
            return (
              <label
                key={company}
                className={`flex cursor-pointer items-center gap-3 rounded-2xl border px-4 py-3 transition ${
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
                <span className="text-sm font-medium">{company}</span>
              </label>
            );
          })}
        </div>
        {selectedCompanies.length === 0 && (
          <p className="mt-3 text-xs text-slate">
            未选择时将搜索所有公司
          </p>
        )}
      </section>
    </aside>
  );
}
