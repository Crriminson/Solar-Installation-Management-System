/*
  Routes.

  One place listing every screen in the app and the URL it lives at.
  Add a route here when you add a page.
*/

import { Routes, Route } from "react-router-dom";

import { EmptyMessage } from "./components/StateMessage";
import LoginPage from "./features/auth/LoginPage";
import RequireStaff from "./features/auth/RequireStaff";
import PackageList from "./features/catalogue/PackageList";
import PackageRecord from "./features/catalogue/PackageRecord";
import ProductForm from "./features/catalogue/ProductForm";
import ProductList from "./features/catalogue/ProductList";
import EnquiryForm from "./features/enquiries/EnquiryForm";
import SalesQueue from "./features/enquiries/SalesQueue";
import SurveyList from "./features/surveys/SurveyList";
import SurveyRecord from "./features/surveys/SurveyRecord";
import SurveyStepForm from "./features/surveys/SurveyStepForm";
import MyWorkPage from "./features/work/MyWorkPage";
import QuotationList from "./features/quotations/quotation_list";
import QuotationRecord from "./features/quotations/quotation_record";
import QuotationGenerate from "./features/quotations/quotation_generate";
import QuotationAccept from "./features/quotations/quotation_accept";
import OrderList from "./features/orders/order_list";
import OrderRecord from "./features/orders/order_record";
import PurchaseList from "./features/inventory/purchase_list";
import PurchaseCreate from "./features/inventory/purchase_create";
import PurchaseRecord from "./features/inventory/purchase_record";
import StockList from "./features/inventory/stock_list";
import FulfilmentList from "./features/fulfilment/fulfilment_list";
import PackingScreen from "./features/fulfilment/packing_screen";

export default function App() {
  return (
    <Routes>
      {/* Public: the enquiry form anyone can reach. */}
      <Route path="/" element={<EnquiryForm />} />
      <Route path="/login" element={<LoginPage />} />

      {/* Staff: inside the app frame, after signing in. */}
      <Route element={<RequireStaff />}>
        <Route path="/work" element={<MyWorkPage />} />
        <Route path="/quotations" element={<QuotationList />} />
        <Route path="/quotations/new" element={<QuotationGenerate />} />
        <Route path="/quotations/:quoteId" element={<QuotationRecord />} />
        <Route path="/quotations/:quoteId/accept" element={<QuotationAccept />} />
        <Route path="/orders" element={<OrderList />} />
        <Route path="/orders/:orderId" element={<OrderRecord />} />
        <Route path="/purchasing" element={<PurchaseList />} />
        <Route path="/purchasing/new" element={<PurchaseCreate />} />
        <Route path="/purchasing/:purchaseId" element={<PurchaseRecord />} />
        <Route path="/stock" element={<StockList />} />
        <Route path="/packing" element={<FulfilmentList />} />
        <Route path="/packing/:fulfilmentId" element={<PackingScreen />} />
        <Route path="/surveys/:surveyId/edit/:revisionId" element={<SurveyStepForm />} />
        <Route path="/enquiries" element={<SalesQueue />} />
        <Route path="/enquiries/new" element={<EnquiryForm staff />} />
        <Route path="/surveys" element={<SurveyList />} />
        <Route path="/surveys/:surveyId" element={<SurveyRecord />} />
        <Route path="/surveys/:surveyId/new" element={<SurveyStepForm />} />
        <Route path="/catalogue/products" element={<ProductList />} />
        <Route path="/catalogue/products/new" element={<ProductForm />} />
        <Route path="/catalogue/products/:productId/edit" element={<ProductForm />} />
        <Route path="/catalogue/packages" element={<PackageList />} />
        <Route path="/catalogue/packages/:packageId" element={<PackageRecord />} />
      </Route>

      <Route path="*" element={<EmptyMessage>This page does not exist.</EmptyMessage>} />
    </Routes>
  );
}
