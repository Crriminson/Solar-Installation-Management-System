/*
  Routes.

  One place listing every screen in the app and the URL it lives at.
  Add a route here when you add a page.
*/

import { Routes, Route } from "react-router-dom";

import NotFound from "./components/NotFound";
import InboxPage from "./features/messaging/inbox_page";
import PublicLinkPage from "./features/messaging/public_link";
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
import JobList from "./features/scheduling/job_list";
import JobCreate from "./features/scheduling/job_create";
import JobRecord from "./features/scheduling/job_record";
import InstallationForm from "./features/installations/installation_form";
import InstallationAccept from "./features/installations/installation_accept";
import WarrantyList from "./features/warranties/warranty_list";
import WarrantyRecord from "./features/warranties/warranty_record";
import TicketList from "./features/support/ticket_list";
import TicketNew from "./features/support/ticket_new";
import TicketRecord from "./features/support/ticket_record";
import TechnicianPay from "./features/costing/technician_pay";
import DashboardPage from "./features/dashboard/dashboard_page";
import MetricPage from "./features/dashboard/metric_page";

export default function App() {
  return (
    <Routes>
      {/* Public: the enquiry form anyone can reach. */}
      <Route path="/" element={<EnquiryForm />} />
      <Route path="/login" element={<LoginPage />} />

      {/* Opened from Telegram. No session: the token is the whole
          authorisation, and the server decides what it is worth. */}
      <Route path="/sign/:token" element={<PublicLinkPage />} />
      <Route path="/confirm/:token" element={<PublicLinkPage />} />

      {/* Staff: inside the app frame, after signing in. */}
      <Route element={<RequireStaff />}>
        <Route path="/work" element={<MyWorkPage />} />
        <Route path="/quotations" element={<QuotationList />} />
        <Route path="/quotations/new" element={<QuotationGenerate />} />
        <Route path="/quotations/:quoteId" element={<QuotationRecord />} />
        <Route path="/orders" element={<OrderList />} />
        <Route path="/orders/:orderId" element={<OrderRecord />} />
        <Route path="/purchasing" element={<PurchaseList />} />
        <Route path="/purchasing/new" element={<PurchaseCreate />} />
        <Route path="/purchasing/:purchaseId" element={<PurchaseRecord />} />
        <Route path="/stock" element={<StockList />} />
        <Route path="/packing" element={<FulfilmentList />} />
        <Route path="/packing/:fulfilmentId" element={<PackingScreen />} />
        <Route path="/schedule" element={<JobList />} />
        <Route path="/schedule/new" element={<JobCreate />} />
        <Route path="/schedule/:jobId" element={<JobRecord />} />
        <Route path="/installations/:reportId" element={<InstallationForm />} />
        <Route path="/warranties" element={<WarrantyList />} />
        <Route path="/warranties/:warrantyId" element={<WarrantyRecord />} />
        <Route path="/inbox" element={<InboxPage />} />
        <Route path="/tickets" element={<TicketList />} />
        <Route path="/tickets/new" element={<TicketNew />} />
        <Route path="/tickets/:ticketId" element={<TicketRecord />} />
        <Route path="/technician-pay" element={<TechnicianPay />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/dashboard/:metricKey" element={<MetricPage />} />
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

      {/* Signed in, but with no staff navigation: these are the screens
          the customer is handed the device on (F06, F11). */}
      <Route element={<RequireStaff chrome={false} />}>
        <Route path="/quotations/:quoteId/accept" element={<QuotationAccept />} />
        <Route path="/installations/:reportId/accept" element={<InstallationAccept />} />
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
