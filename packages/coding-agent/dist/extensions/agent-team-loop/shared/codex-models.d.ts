import type { Api, Model } from "@earendil-works/pi-ai";
export interface LocalCodexCatalog {
    models: Model<Api>[];
    source: string;
    warning?: string;
}
/** Copy only model metadata. Never read credentials or expose cached model instructions. */
export declare function readLocalCodexModels(baseUrl: string, codexHome?: string): LocalCodexCatalog;
//# sourceMappingURL=codex-models.d.ts.map