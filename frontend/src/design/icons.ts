/*
  The app's icon set.

  Every icon in the app is imported from here, never straight from the
  library. Two reasons: one visual family across every screen, and one
  file to change if the library ever changes.

  Names are what the icon means in this product, not what the library
  calls it, so "the icon for an order" is a question with one answer.

  Accessibility: an icon beside its own label is decorative and takes
  aria-hidden. An icon that is the only content of a control needs the
  control to carry the label. Defaults for size and weight are set once
  in IconDefaults below.
*/

export {
  /* Navigation */
  ListChecks as MyWorkIcon,
  Gauge as DashboardIcon,
  FileText as QuotationIcon,
  Tray as EnquiryIcon,
  ClipboardText as SurveyIcon,
  Receipt as OrderIcon,
  Package as PackingIcon,
  Calendar as ScheduleIcon,
  Storefront as StockIcon,
  Truck as PurchasingIcon,
  Wrench as TicketIcon,
  ShieldCheck as WarrantyIcon,
  CurrencyInr as FinanceIcon,
  Barcode as ProductIcon,
  Toolbox as PackageTemplateIcon,

  /* Account and shell */
  UserCircle as AccountIcon,
  SignOut as SignOutIcon,
  List as MenuIcon,
  DotsThree as MoreIcon,
  SlidersHorizontal as SettingsIcon,

  /* Direction */
  CaretRight as CaretRightIcon,
  CaretLeft as CaretLeftIcon,
  CaretDown as CaretDownIcon,
  CaretUp as CaretUpIcon,
  ArrowRight as ArrowRightIcon,
  ArrowLeft as ArrowLeftIcon,
  ArrowSquareOut as OpenRecordIcon,

  /* Actions */
  Plus as AddIcon,
  X as CloseIcon,
  Check as ConfirmIcon,
  MagnifyingGlass as SearchIcon,
  Funnel as FilterIcon,
  PencilSimple as EditIcon,
  DownloadSimple as DownloadIcon,
  FileCsv as CsvIcon,
  FilePdf as PdfIcon,
  Camera as CameraIcon,
  Signature as SignatureIcon,
  ArrowsClockwise as RetryIcon,
  PaperPlaneTilt as SendIcon,
  ChatCircle as ChatIcon,
  ChatCircleDots as AssistantIcon,
  Stop as StopIcon,
  CircleNotch as SpinnerIcon,

  /* Status and meaning */
  Warning as WarningIcon,
  WarningCircle as BlockedIcon,
  Info as InfoIcon,
  SealCheck as DoneIcon,
  Prohibit as ForbiddenIcon,
  Clock as PendingIcon,
  ListDashes as EmptyIcon,
  TrendUp as RiseIcon,
  TrendDown as FallIcon,

  /* Records */
  Users as CustomerIcon,
  Buildings as SiteIcon,
  MapPin as AddressIcon,
  Phone as PhoneIcon,
  HardHat as TechnicianIcon,
  Lightning as CapacityIcon,
  Sun as GenerationIcon,
} from "@phosphor-icons/react";

export { IconContext as IconDefaults } from "@phosphor-icons/react";

/*
  Sizes. An icon beside text matches the text's cap height rather than
  its font size, which is why these are smaller than they look.
*/
export const ICON_SIZE = {
  inline: 15, // inside a sentence or a badge
  control: 17, // in a button or a nav item
  section: 20, // beside a section title
  feature: 32, // an empty state or a metric card
} as const;
