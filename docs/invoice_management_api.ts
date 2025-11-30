/**
 * Invoice Management API Endpoints
 * Ready-to-use Express routes for Invoice Management
 * 
 * Copy this file to: src/routes/invoice.routes.ts
 * 
 * Dependencies:
 * npm install express multer
 * npm install -D @types/express @types/multer
 */

import { Router, Request, Response, NextFunction } from 'express';
import multer from 'multer';
import { format } from 'date-fns';
import { InvoiceParserService } from '../services/invoice-parser.service';
import {
  Invoice,
  ListInvoicesParams,
  InvoiceStatus,
  PaymentType,
  Currency,
} from '../types/invoice.types';

// ============================================
// TYPE DEFINITIONS
// ============================================

interface AuthenticatedRequest extends Request {
  user?: {
    email: string;
    id: string;
  };
}

interface ApproveInvoiceBody {
  scheduledDate?: string;
  notes?: string;
}

interface RejectInvoiceBody {
  reason: string;
}

interface UpdateInvoiceBody {
  vendorName?: string;
  invoiceNumber?: string;
  amount?: number;
  currency?: Currency;
  invoiceDate?: string;
  dueDate?: string;
  description?: string;
  category?: string;
  paymentType?: PaymentType;
  scheduledDate?: string;
}

// ============================================
// MIDDLEWARE
// ============================================

/**
 * Authentication middleware - Replace with your auth system
 */
const loginRequired = (req: AuthenticatedRequest, res: Response, next: NextFunction): void => {
  const userEmail = req.headers['x-user-email'] as string || (req as any).session?.user_email;
  
  if (!userEmail) {
    res.status(401).json({ status: 'error', message: 'Authentication required' });
    return;
  }
  
  req.user = { email: userEmail, id: userEmail };
  next();
};

/**
 * Get user email from request
 */
const getUserEmail = (req: AuthenticatedRequest): string => {
  return req.user?.email || 'unknown@example.com';
};

// ============================================
// ROUTER SETUP
// ============================================

const router = Router();
const upload = multer({ storage: multer.memoryStorage() });
const invoiceService = new InvoiceParserService();

// Apply auth middleware to all routes
router.use(loginRequired);

// ============================================
// UPLOAD ENDPOINTS
// ============================================

/**
 * POST /api/invoices/upload
 * Upload and parse a single invoice PDF
 * 
 * Request: multipart/form-data with 'file' field
 * Response: {
 *   status: 'success',
 *   invoiceId: 'INV-2024-001',
 *   extractedData: { vendorName, amount, ... },
 *   confidence: 0.95
 * }
 */
router.post(
  '/upload',
  upload.single('file'),
  async (req: AuthenticatedRequest, res: Response, next: NextFunction): Promise<void> => {
    try {
      const file = req.file;
      
      if (!file) {
        res.status(400).json({ status: 'error', message: 'No file provided' });
        return;
      }

      if (file.originalname === '') {
        res.status(400).json({ status: 'error', message: 'No file selected' });
        return;
      }

      const allowedTypes = ['application/pdf', 'image/png', 'image/jpeg', 'image/jpg'];
      if (!allowedTypes.includes(file.mimetype)) {
        res.status(400).json({ status: 'error', message: 'Invalid file type. Allowed: PDF, PNG, JPG' });
        return;
      }

      const userEmail = getUserEmail(req);
      const result = await invoiceService.parseInvoice(
        file.buffer,
        file.originalname,
        file.mimetype,
        userEmail
      );

      res.json(result);
    } catch (error) {
      console.error('Invoice upload error:', error);
      res.status(500).json({
        status: 'error',
        message: error instanceof Error ? error.message : 'Upload failed',
      });
    }
  }
);

/**
 * POST /api/invoices/upload/bulk
 * Upload and parse multiple invoice PDFs
 * 
 * Request: multipart/form-data with 'files[]' field (multiple files)
 * Response: {
 *   status: 'success',
 *   total: 5,
 *   processed: 4,
 *   failed: 1,
 *   results: [{ filename, status, invoiceId, vendorName, amount, error }]
 * }
 */
router.post(
  '/upload/bulk',
  upload.array('files[]', 50),
  async (req: AuthenticatedRequest, res: Response, next: NextFunction): Promise<void> => {
    try {
      const files = req.files as Express.Multer.File[];

      if (!files || files.length === 0) {
        res.status(400).json({ status: 'error', message: 'No files provided' });
        return;
      }

      if (files.every((f) => f.originalname === '')) {
        res.status(400).json({ status: 'error', message: 'No files selected' });
        return;
      }

      const allowedTypes = ['application/pdf', 'image/png', 'image/jpeg', 'image/jpg'];
      const validFiles = files
        .filter((f) => allowedTypes.includes(f.mimetype))
        .map((f) => ({
          buffer: f.buffer,
          filename: f.originalname,
          mimeType: f.mimetype,
        }));

      if (validFiles.length === 0) {
        res.status(400).json({ status: 'error', message: 'No valid files provided' });
        return;
      }

      const userEmail = getUserEmail(req);
      const result = await invoiceService.parseInvoicesBulk(validFiles, userEmail);

      res.json(result);
    } catch (error) {
      console.error('Bulk upload error:', error);
      res.status(500).json({
        status: 'error',
        message: error instanceof Error ? error.message : 'Bulk upload failed',
      });
    }
  }
);

// ============================================
// LIST & GET ENDPOINTS
// ============================================

/**
 * GET /api/invoices
 * Get paginated list of invoices with filters
 * 
 * Query Parameters:
 *   - page: number (default 1)
 *   - limit: number (default 50)
 *   - status: pending|approved|rejected|paid
 *   - paymentType: Wire|ACH|Card|PayPal|Venmo|Crypto
 *   - currency: USD|EUR|GBP|...
 *   - dateFrom: YYYY-MM-DD
 *   - dateTo: YYYY-MM-DD
 *   - search: string (vendor name, invoice number)
 *   - sortBy: createdAt|invoiceDate|amount|vendorName|status
 *   - sortOrder: asc|desc
 */
router.get(
  '/',
  async (req: AuthenticatedRequest, res: Response, next: NextFunction): Promise<void> => {
    try {
      const userEmail = getUserEmail(req);

      const params: ListInvoicesParams = {
        page: parseInt(req.query.page as string) || 1,
        limit: parseInt(req.query.limit as string) || 50,
        status: req.query.status as InvoiceStatus | undefined,
        paymentType: req.query.paymentType as PaymentType | undefined,
        currency: req.query.currency as Currency | undefined,
        dateFrom: req.query.dateFrom as string | undefined,
        dateTo: req.query.dateTo as string | undefined,
        search: req.query.search as string | undefined,
        sortBy: req.query.sortBy as ListInvoicesParams['sortBy'],
        sortOrder: req.query.sortOrder as 'asc' | 'desc' | undefined,
      };

      const result = await invoiceService.listInvoices(userEmail, params);
      res.json(result);
    } catch (error) {
      console.error('List invoices error:', error);
      res.status(500).json({
        status: 'error',
        message: error instanceof Error ? error.message : 'Failed to list invoices',
      });
    }
  }
);

/**
 * GET /api/invoices/summary
 * Get invoice summary statistics
 * 
 * Response: {
 *   status: 'success',
 *   summary: {
 *     totalPending: 12,
 *     totalDue: 47890,
 *     overdue: 3,
 *     awaitingApproval: 5,
 *     paidThisMonth: 124500,
 *     scheduled: 4
 *   }
 * }
 */
router.get(
  '/summary',
  async (req: AuthenticatedRequest, res: Response, next: NextFunction): Promise<void> => {
    try {
      const userEmail = getUserEmail(req);
      const result = await invoiceService.getSummary(userEmail);
      res.json(result);
    } catch (error) {
      console.error('Summary error:', error);
      res.status(500).json({
        status: 'error',
        message: error instanceof Error ? error.message : 'Failed to get summary',
      });
    }
  }
);

/**
 * GET /api/invoices/export
 * Export invoices to CSV
 * 
 * Query Parameters: Same filters as list invoices
 * Response: CSV file download
 */
router.get(
  '/export',
  async (req: AuthenticatedRequest, res: Response, next: NextFunction): Promise<void> => {
    try {
      const userEmail = getUserEmail(req);

      const params: ListInvoicesParams = {
        limit: 10000,
        status: req.query.status as InvoiceStatus | undefined,
        dateFrom: req.query.dateFrom as string | undefined,
        dateTo: req.query.dateTo as string | undefined,
      };

      const { invoices } = await invoiceService.listInvoices(userEmail, params);

      const headers = [
        'Invoice ID',
        'Invoice Number',
        'Vendor',
        'Amount',
        'Currency',
        'Invoice Date',
        'Due Date',
        'Status',
        'Payment Type',
        'Category',
        'Description',
      ];

      const rows = invoices.map((inv) => [
        inv.invoiceId,
        inv.invoiceNumber || '',
        inv.vendorName,
        inv.amount,
        inv.currency,
        inv.invoiceDate || '',
        inv.dueDate || '',
        inv.status,
        inv.paymentType || '',
        inv.category || '',
        (inv.description || '').replace(/,/g, ';'),
      ]);

      const csv = [headers, ...rows].map((row) => row.join(',')).join('\n');
      const filename = `invoices_${format(new Date(), 'yyyyMMdd')}.csv`;

      res.setHeader('Content-Type', 'text/csv');
      res.setHeader('Content-Disposition', `attachment; filename=${filename}`);
      res.send(csv);
    } catch (error) {
      console.error('Export error:', error);
      res.status(500).json({
        status: 'error',
        message: error instanceof Error ? error.message : 'Export failed',
      });
    }
  }
);

/**
 * GET /api/invoices/:invoiceId
 * Get detailed invoice information
 */
router.get(
  '/:invoiceId',
  async (req: AuthenticatedRequest, res: Response, next: NextFunction): Promise<void> => {
    try {
      const { invoiceId } = req.params;
      const result = await invoiceService.getInvoice(invoiceId);

      if (!result) {
        res.status(404).json({ status: 'error', message: 'Invoice not found' });
        return;
      }

      res.json({ status: 'success', invoice: result });
    } catch (error) {
      console.error('Get invoice error:', error);
      res.status(500).json({
        status: 'error',
        message: error instanceof Error ? error.message : 'Failed to get invoice',
      });
    }
  }
);

// ============================================
// UPDATE ENDPOINTS
// ============================================

/**
 * PUT /api/invoices/:invoiceId
 * Update invoice data
 */
router.put(
  '/:invoiceId',
  async (req: AuthenticatedRequest, res: Response, next: NextFunction): Promise<void> => {
    try {
      const { invoiceId } = req.params;
      const data: UpdateInvoiceBody = req.body;
      const userEmail = getUserEmail(req);

      const result = await invoiceService.updateInvoice(invoiceId, data, userEmail);
      res.json(result);
    } catch (error) {
      console.error('Update invoice error:', error);
      res.status(500).json({
        status: 'error',
        message: error instanceof Error ? error.message : 'Update failed',
      });
    }
  }
);

// ============================================
// APPROVAL WORKFLOW ENDPOINTS
// ============================================

/**
 * POST /api/invoices/:invoiceId/approve
 * Approve an invoice for payment
 * 
 * Request Body: {
 *   scheduledDate?: 'YYYY-MM-DD',
 *   notes?: 'Approved for payment'
 * }
 */
router.post(
  '/:invoiceId/approve',
  async (req: AuthenticatedRequest, res: Response, next: NextFunction): Promise<void> => {
    try {
      const { invoiceId } = req.params;
      const { scheduledDate, notes }: ApproveInvoiceBody = req.body || {};
      const userEmail = getUserEmail(req);

      const result = await invoiceService.approveInvoice(
        invoiceId,
        userEmail,
        scheduledDate,
        notes
      );

      res.json(result);
    } catch (error) {
      console.error('Approve invoice error:', error);
      res.status(500).json({
        status: 'error',
        message: error instanceof Error ? error.message : 'Approval failed',
      });
    }
  }
);

/**
 * POST /api/invoices/:invoiceId/reject
 * Reject an invoice
 * 
 * Request Body: {
 *   reason: 'Duplicate invoice' (required)
 * }
 */
router.post(
  '/:invoiceId/reject',
  async (req: AuthenticatedRequest, res: Response, next: NextFunction): Promise<void> => {
    try {
      const { invoiceId } = req.params;
      const { reason }: RejectInvoiceBody = req.body || {};

      if (!reason) {
        res.status(400).json({ status: 'error', message: 'Rejection reason required' });
        return;
      }

      const userEmail = getUserEmail(req);
      const result = await invoiceService.rejectInvoice(invoiceId, userEmail, reason);

      res.json(result);
    } catch (error) {
      console.error('Reject invoice error:', error);
      res.status(500).json({
        status: 'error',
        message: error instanceof Error ? error.message : 'Rejection failed',
      });
    }
  }
);

// ============================================
// DOWNLOAD ENDPOINT
// ============================================

/**
 * GET /api/invoices/:invoiceId/download
 * Get signed URL to download original invoice PDF
 * 
 * Response: {
 *   status: 'success',
 *   downloadUrl: 'https://storage.googleapis.com/...',
 *   expiresIn: 3600
 * }
 */
router.get(
  '/:invoiceId/download',
  async (req: AuthenticatedRequest, res: Response, next: NextFunction): Promise<void> => {
    try {
      const { invoiceId } = req.params;
      const url = await invoiceService.getDownloadUrl(invoiceId);

      if (!url) {
        res.status(404).json({ status: 'error', message: 'PDF not found' });
        return;
      }

      res.json({
        status: 'success',
        downloadUrl: url,
        expiresIn: 3600,
      });
    } catch (error) {
      console.error('Download error:', error);
      res.status(500).json({
        status: 'error',
        message: error instanceof Error ? error.message : 'Download failed',
      });
    }
  }
);

// ============================================
// EXPORT
// ============================================

export default router;

/**
 * Register routes with Express app
 * 
 * Usage:
 * import invoiceRoutes from './routes/invoice.routes';
 * app.use('/api/invoices', invoiceRoutes);
 */
export { router as invoiceRouter };
