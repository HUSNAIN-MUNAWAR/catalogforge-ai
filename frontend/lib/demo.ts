export type Product = {
  id: string; title: string; sku: string; brand: string; category: string; price: number; inventory: number;
  barcode: string; image: string; status: "Approved" | "Needs review" | "Blocked" | "Published";
  confidence: number; material: string; color: string; dimensions: string; weight: string;
};
export const products: Product[] = [
  { id:"cf-101", title:"Woven Storage Basket — Natural", sku:"CF-001001", brand:"Northern Atelier", category:"Home / Storage", price:32, inventory:48, barcode:"89010100101", image:"/demo_data/product_images/product_01.svg", status:"Needs review", confidence:.96, material:"Seagrass", color:"Natural", dimensions:"38 × 28 cm", weight:"0.84 kg" },
  { id:"cf-102", title:"Woven Storage Basket — Natural / 2-pack", sku:"CF-001002", brand:"Northern Atelier", category:"Home / Storage", price:58, inventory:24, barcode:"89010100102", image:"/demo_data/product_images/product_02.svg", status:"Needs review", confidence:.94, material:"Seagrass", color:"Natural", dimensions:"38 × 28 cm", weight:"1.68 kg" },
  { id:"cf-103", title:"Ceramic Pouring Bowl — Cloud", sku:"", brand:"Northern Atelier", category:"Kitchen / Serveware", price:420, inventory:2, barcode:"89010100103", image:"/demo_data/product_images/product_03.svg", status:"Needs review", confidence:.72, material:"Ceramic", color:"Cloud", dimensions:"21 × 18 cm", weight:"1.42 kg" },
  { id:"cf-104", title:"Linen Table Runner — Sage", sku:"CF-001004", brand:"Northern Atelier", category:"Home / Table Linen", price:18, inventory:80, barcode:"89010100104", image:"/demo_data/product_images/product_04.svg", status:"Approved", confidence:.93, material:"Linen", color:"Sage", dimensions:"220 × 35 cm", weight:"0.26 kg" },
  { id:"cf-105", title:"Oak Serving Board — Natural", sku:"CF-001005", brand:"Harbor & Field", category:"Kitchen / Boards", price:46, inventory:24, barcode:"89010100105", image:"/demo_data/product_images/product_05.svg", status:"Approved", confidence:.95, material:"Oak", color:"Natural", dimensions:"44 × 21 cm", weight:"1.2 kg" },
  { id:"cf-106", title:"Glass Pantry Jar — Clear", sku:"CF-001006", brand:"Terra Housewares", category:"Kitchen / Storage", price:16, inventory:120, barcode:"89010100106", image:"/demo_data/product_images/product_06.svg", status:"Published", confidence:.91, material:"Borosilicate glass", color:"Clear", dimensions:"14 × 14 cm", weight:"0.52 kg" },
  { id:"cf-107", title:"Cotton Napkin Set — Parchment", sku:"CF-001007", brand:"Morrow Textiles", category:"Home / Table Linen", price:24, inventory:96, barcode:"89010100107", image:"/demo_data/product_images/product_07.svg", status:"Approved", confidence:.89, material:"Cotton", color:"Parchment", dimensions:"45 × 45 cm", weight:"0.36 kg" },
  { id:"cf-108", title:"Brass Table Lamp — Ink", sku:"CF-001008", brand:"Lumen Living", category:"Lighting / Table Lamps", price:145, inventory:8, barcode:"89010100108", image:"/demo_data/product_images/product_08.svg", status:"Blocked", confidence:.77, material:"Brass", color:"Ink", dimensions:"32 × 18 cm", weight:"2.4 kg" },
];
export const intakeJobs = [
  {id:"job-na-72", file:"Synthetic_Northern_Atelier_Catalog_01.pdf", vendor:"Northern Atelier", type:"PDF catalog", status:"Needs review", products:72, confidence:82, failures:5, reviewer:"Avery Chen", destination:"Shopify mock", age:"12 min ago"},
  {id:"job-hf-19", file:"Synthetic_vendor_export_02.csv", vendor:"Harbor & Field", type:"CSV", status:"Extracted", products:19, confidence:96, failures:0, reviewer:"Maya Torres", destination:"PIM export", age:"42 min ago"},
  {id:"job-ms-28", file:"Synthetic_product_sheet_04.xlsx", vendor:"Morrow Textiles", type:"Spreadsheet", status:"Blocked", products:28, confidence:74, failures:7, reviewer:"Avery Chen", destination:"WooCommerce mock", age:"1 hr ago"},
  {id:"job-th-14", file:"Synthetic_Invoice_03.pdf", vendor:"Terra Housewares", type:"Invoice / PO", status:"Approved", products:14, confidence:91, failures:1, reviewer:"Maya Torres", destination:"Shopify mock", age:"2 hr ago"},
  {id:"job-lg-22", file:"Synthetic_product_photo_batch_01.svg", vendor:"Lumen Living", type:"Image batch", status:"Processing", products:22, confidence:0, failures:0, reviewer:"Unassigned", destination:"Shopify mock", age:"2 hr ago"},
  {id:"job-jg-37", file:"Synthetic_Juniper_Goods_Catalog_06.pdf", vendor:"Juniper Goods", type:"PDF catalog", status:"Published", products:37, confidence:95, failures:0, reviewer:"Maya Torres", destination:"Shopify mock", age:"yesterday"},
];
export const vendors = [
  ["Northern Atelier", "VND-001", 9, 148, "82%", "Missing SKU"], ["Harbor & Field", "VND-002", 6, 92, "96%", "None"], ["Alder Supply Co.", "VND-003", 5, 74, "91%", "Image quality"], ["Morrow Textiles", "VND-004", 7, 123, "86%", "Title format"], ["Mason & Vale", "VND-005", 4, 59, "93%", "Barcode"], ["Terra Housewares", "VND-006", 8, 111, "89%", "Price anomaly"], ["Juniper Goods", "VND-007", 6, 88, "94%", "None"], ["Lumen Living", "VND-008", 5, 76, "78%", "Low confidence"],
];
export const audits = [
  ["2 min ago","Avery Chen","field.corrected","CF-001003","SKU set to NA-0103"], ["8 min ago","Maya Torres","duplicate.separated","DUP-0041","Pack size verified"], ["12 min ago","System","document.extracted","job-na-72","72 candidate records created"], ["18 min ago","Avery Chen","validation.overridden","CF-001105","Vendor price confirmation added"], ["34 min ago","System","publication.completed","PUB-050","18 products sent to Shopify mock"],
];
export const confidenceBars = [{label:"95–100%",value:156,pct:72},{label:"85–94%",value:224,pct:100},{label:"70–84%",value:108,pct:48},{label:"<70%",value:32,pct:14}];
export function statusTone(value: string) { const v = value.toLowerCase(); if (v.includes("approved") || v.includes("published") || v.includes("completed")) return "badge-green"; if (v.includes("review") || v.includes("processing") || v.includes("received")) return "badge-amber"; if (v.includes("blocked") || v.includes("failed")) return "badge-coral"; return "badge-blue"; }
