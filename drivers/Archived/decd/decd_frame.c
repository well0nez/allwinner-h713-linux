// SPDX-License-Identifier: GPL-2.0

#include <linux/debugfs.h>
#include <linux/dma-buf.h>
#include <linux/highmem.h>
#include <linux/mm.h>
#include <linux/of_reserved_mem.h>
#include <linux/printk.h>
#include <linux/seq_file.h>
#include <linux/slab.h>
#include <linux/vmalloc.h>

#include "decd_types.h"

static LIST_HEAD(dec_video_info_free_list);
static LIST_HEAD(dec_video_info_used_list);
static DEFINE_SPINLOCK(dec_video_info_lock);
static void *video_info_block_start;
static struct dentry *video_buffer_dbg_dir;
static struct device *video_buffer_dev;
static size_t video_buffer_last_size;
static u32 video_buffer_last_phys;
static u32 video_buffer_last_dma;
static void __iomem *dec_debug_reg_base;
static LIST_HEAD(video_buffer_export_list);
static DEFINE_SPINLOCK(video_buffer_export_lock);

struct video_buffer_export {
	struct list_head node;
	struct dma_buf *dbuf;
	struct dma_buf_attachment *attach;
	struct sg_table *sgt;
	u32 phys;
	u32 size;
	u32 dma_addr;
	struct sg_table backing;
};

static void dec_debug_work_func(struct work_struct *work)
{
	struct dec_debug_info *dbg = container_of(work, struct dec_debug_info, work);
	int i;
	u32 pos;

	printk("DEC debug dump begin\n");
	print_hex_dump(KERN_ERR, "DEC_DEBUG ", DUMP_PREFIX_OFFSET, 16, 4,
		       dbg->dbgdat + 2, 512, false);
	printk("frame ring wpos=%u\n", dbg->frame_trace_pos & 0x3f);
	for (i = 0; i < 64; i++)
		printk("frame[%02d]=%08x %08x\n", i,
		       dbg->dbgdat[130 + i * 2], dbg->dbgdat[131 + i * 2]);
	pos = dbg->jiffies_pos & 0x3f;
	printk("jiffies ring wpos=%u\n", pos);
	for (i = 0; i < 64; i++)
		printk("jiffies[%02d]=%08x %08x %08x\n", i,
		       dbg->dbgdat[262 + i * 7],
		       dbg->dbgdat[263 + i * 7],
		       dbg->dbgdat[264 + i * 7]);
}

int dec_debug_set_register_base(int base)
{
	dec_debug_reg_base = (void __iomem *)(uintptr_t)base;
	return base;
}

int dec_debug_record_exception(int a1, int a2)
{
	struct dec_debug_info *dbg;
	u32 pos;

	if (!g_dec || !g_dec->debug || !dec_debug_reg_base)
		return -EINVAL;
	dbg = g_dec->debug;
	memcpy_fromio(dbg->dbgdat + 2, dec_debug_reg_base, 512);
	pos = dbg->exception_trace_pos & 0x3f;
	dbg->exception_trace_pos++;
	dbg->dbgdat[262 + pos * 7] = a1;
	dbg->dbgdat[263 + pos * 7] = a2;
	dbg->dbgdat[264 + pos * 7] = jiffies;
	return queue_work_on(4, system_wq, &dbg->work);
}

int dec_debug_trace_frame(int addr, int fmt)
{
	struct dec_debug_info *dbg;
	u32 pos;

	if (!g_dec || !g_dec->debug)
		return addr;
	dbg = g_dec->debug;
	pos = dbg->frame_trace_pos & 0x3f;
	dbg->frame_trace_pos++;
	dbg->dbgdat[130 + pos * 2] = addr;
	dbg->dbgdat[131 + pos * 2] = fmt;
	return addr;
}

/*
 * dec_debug_trace_dma_buf_map — IDA 0x7300
 *
 * IDA: (map_ptr, dma_addr, buf_size, video_info_ptr)
 * Writes into dbgdat ring at offset 261+i*7 under spinlock.
 * Our port simplifies: we store the basic trace info.
 */
void dec_debug_trace_dma_buf_map(struct dec_frame_item *item)
{
	struct dec_debug_info *dbg;
	u32 pos;

	if (!item || !item->image_map || !g_dec || !g_dec->debug)
		return;
	dbg = g_dec->debug;
	pos = dbg->exception_trace_pos & 0x3f;
	dbg->dbgdat[262 + pos * 7] = item->image_map->dma_addr;
	dbg->dbgdat[263 + pos * 7] = dec_dma_buf_size(item->image_map);
	dbg->dbgdat[261 + pos * 7] = (u32)(uintptr_t)item->image_map;
	dbg->dbgdat[267 + pos * 7] = 1; /* active flag */
	if (item->video_info_page) {
		struct dec_video_info_page *vp = item->video_info_page;
		dbg->dbgdat[264 + pos * 7] = ((u32 *)vp->vaddr)[4];
		dbg->dbgdat[265 + pos * 7] = ((u32 *)vp->vaddr)[5];
		dbg->dbgdat[266 + pos * 7] = ((u32 *)vp->vaddr)[16];
	}
	dbg->exception_trace_pos++;
}

/*
 * dec_debug_trace_dma_buf_unmap — IDA 0x73ac
 *
 * IDA: (map_ptr, dma_addr) — searches ring for matching entry,
 * clears active flag [267+i*7] = 0.
 */
void dec_debug_trace_dma_buf_unmap(struct dec_frame_item *item)
{
	struct dec_debug_info *dbg;
	int i;

	if (!item || !item->image_map || !g_dec || !g_dec->debug)
		return;
	dbg = g_dec->debug;
	for (i = 0; i < 64; i++) {
		if (dbg->dbgdat[261 + i * 7] == (u32)(uintptr_t)item->image_map &&
		    dbg->dbgdat[262 + i * 7] == (u32)item->image_map->dma_addr) {
			dbg->dbgdat[267 + i * 7] = 0;
			break;
		}
	}
}

int dec_debug_dump(int dst, int len, int a3, int a4)
{
	char *buf = (char *)(uintptr_t)dst;
	int out;
	int i;

	if (!g_dec || !g_dec->debug)
		return 0;
	out = hex_dump_to_buffer(g_dec->debug->dbgdat + 2, 512, 16, 4,
				 buf, len, false);
	out += sprintf(buf + out, "\nframe info: wpos=%d\n",
		       g_dec->debug->frame_trace_pos);
	for (i = 0; i < 64; i++)
		out += sprintf(buf + out, "[%02d] %08x %d\n", i,
			       g_dec->debug->dbgdat[130 + i * 2],
			       g_dec->debug->dbgdat[131 + i * 2]);
	for (i = 0; i < 64; i++)
		out += sprintf(buf + out, "exc[%02d] %08x %08x %08x\n", i,
			       g_dec->debug->dbgdat[262 + i * 7],
			       g_dec->debug->dbgdat[263 + i * 7],
			       g_dec->debug->dbgdat[264 + i * 7]);
	return out;
}

int dec_debug_init(struct dec_device *dec)
{
	INIT_WORK(&dec->debug->work, dec_debug_work_func);
	dec->debug->frame_trace_pos = 0;
	dec->debug->exception_trace_pos = 0;
	return 0;
}

static int video_buffer_debugfs_show(struct seq_file *s, void *data)
{
	seq_puts(s, "tvdisp video buffer info:\n");
	seq_printf(s, "              size: 0x%08zx\n", video_buffer_last_size);
	seq_printf(s, "  physical address: 0x%08x\n", video_buffer_last_phys);
	seq_printf(s, "     iommu address: 0x%08x\n", video_buffer_last_dma);
	return 0;
}

static int video_buffer_debugfs_open(struct inode *inode, struct file *file)
{
	return single_open(file, video_buffer_debugfs_show, inode->i_private);
}

static const struct file_operations dec_video_buffer_debugfs_fops = {
	.owner = THIS_MODULE,
	.open = video_buffer_debugfs_open,
	.read = seq_read,
	.llseek = seq_lseek,
	.release = single_release,
};

static int video_buffer_init(struct device *dev)
{
	if (video_buffer_dev)
		return 0;
	video_buffer_dev = dev;
	video_buffer_dbg_dir = debugfs_create_dir("video-buffer", NULL);
	debugfs_create_file_unsafe("info", 0444, video_buffer_dbg_dir, NULL,
				   &dec_video_buffer_debugfs_fops);
	return 0;
}

static const struct dma_buf_ops dec_video_buffer_dma_buf_ops = {
	.attach = video_buffer_dma_buf_attach,
	.detach = video_buffer_dma_buf_detatch,
	.map_dma_buf = video_buffer_map_dma_buf,
	.unmap_dma_buf = video_buffer_unmap_dma_buf,
	.release = video_buffer_dma_buf_release,
};

int video_buffer_dma_buf_attach(struct dma_buf *dmabuf,
				struct dma_buf_attachment *attach)
{
	struct sg_table *src;
	struct sg_table *clone;
	struct scatterlist *sg_src;
	struct scatterlist *sg_dst;
	unsigned int i;
	void *helper;

	if (!dmabuf || !attach || !dmabuf->priv)
		return -ENOMEM;

	src = dmabuf->priv;
	helper = kzalloc(12, GFP_KERNEL);
	if (!helper)
		return -ENOMEM;
	clone = kzalloc(sizeof(*clone), GFP_KERNEL);
	if (!clone) {
		kfree(helper);
		return -ENOMEM;
	}
	if (sg_alloc_table(clone, src->nents, GFP_KERNEL)) {
		kfree(clone);
		kfree(helper);
		return -ENOMEM;
	}
	for_each_sg(src->sgl, sg_src, src->nents, i) {
		sg_dst = &clone->sgl[i];
		memcpy(sg_dst, sg_src, sizeof(*sg_dst));
		sg_dma_address(sg_dst) = 0;
	}
	*(void **)helper = attach->dev;
	*((void **)helper + 1) = clone;
	*((u8 *)helper + 8) = 0;
	attach->priv = helper;
	return 0;
}

void video_buffer_dma_buf_detatch(struct dma_buf *dmabuf,
				 struct dma_buf_attachment *attach)
{
	void *helper;
	struct sg_table *sgt;

	if (!attach || !attach->priv)
		return;
	helper = attach->priv;
	sgt = *((void **)helper + 1);
	sg_free_table(sgt);
	kfree(sgt);
	kfree(helper);
	attach->priv = NULL;
}

void video_buffer_dma_buf_release(struct dma_buf *dmabuf)
{
	struct sg_table *sgt;

	if (!dmabuf || !dmabuf->priv)
		return;
	sgt = dmabuf->priv;
	sg_free_table(sgt);
	kfree(sgt);
}

struct sg_table *video_buffer_map_dma_buf(struct dma_buf_attachment *attach,
					 enum dma_data_direction dir)
{
	void *helper;
	struct sg_table *sgt;

	if (!attach || !attach->priv)
		return ERR_PTR(-ENOMEM);
	helper = attach->priv;
	sgt = *((void **)helper + 1);
	*((u8 *)helper + 8) = 1;
	return sgt;
}

void video_buffer_unmap_dma_buf(struct dma_buf_attachment *attach,
				       struct sg_table *sgt,
				       enum dma_data_direction dir)
{
	if (attach && attach->priv)
		*((u8 *)attach->priv + 8) = 0;
}

ssize_t dec_show_info(struct device *dev, struct device_attribute *attr,
		      char *buf)
{
	struct dec_device *dec = dev_get_drvdata(dev);
	int out = 0;
	int i;

	if (!dec)
		return sprintf(buf, "Null dec_device\n");

	out += sprintf(buf + out,
		       "enabled=%d irq=%d clk=%u reset=%d\n",
		       dec->enabled, dec->irq, dec->clk_rate,
		       reset_control_status(dec->rst_bus_disp));
	out += sprintf(buf + out, "top regs:\n");
	for (i = 0; i < 0xa0; i += 16) {
		u32 regbuf[4];
		regbuf[0] = readl(dec->regs->top + i);
		regbuf[1] = readl(dec->regs->top + i + 4);
		regbuf[2] = readl(dec->regs->top + i + 8);
		regbuf[3] = readl(dec->regs->top + i + 12);
		out += hex_dump_to_buffer(regbuf, 16, 16, 4, buf + out,
					 PAGE_SIZE - out, false);
		out += sprintf(buf + out, "\n");
	}
	out += sprintf(buf + out, "afbd regs:\n");
	for (i = 0; i < 0x190; i += 16) {
		u32 regbuf[4];
		regbuf[0] = readl(dec->regs->afbd + i);
		regbuf[1] = readl(dec->regs->afbd + i + 4);
		regbuf[2] = readl(dec->regs->afbd + i + 8);
		regbuf[3] = readl(dec->regs->afbd + i + 12);
		out += hex_dump_to_buffer(regbuf, 16, 16, 4, buf + out,
					 PAGE_SIZE - out, false);
		out += sprintf(buf + out, "\n");
	}
	out += sprintf(buf + out, "\nworkaround=%08x\n",
		       readl(dec->regs->workaround));
	return out;
}

ssize_t dec_show_frame_manager(struct device *dev,
			       struct device_attribute *attr, char *buf)
{
	struct dec_device *dec = dev_get_drvdata(dev);
	int out = 0;
	struct dec_video_info_page *page;

	if (!dec)
		return sprintf(buf, "Null dec_device\n");

	out += sprintf(buf + out, "video-info free list:\n");
	list_for_each_entry(page, &dec_video_info_free_list, node)
		out += sprintf(buf + out, "free idx=%u phys=%pa\n",
			       page->index, &page->paddr);
	out += sprintf(buf + out, "video-info used list:\n");
	list_for_each_entry(page, &dec_video_info_used_list, node)
		out += sprintf(buf + out, "used idx=%u phys=%pa\n",
			       page->index, &page->paddr);
	if (dec->fmgr)
		out += dec_frame_manager_dump(dec->fmgr, buf + out);
	return out;
}

int video_buffer_map(u32 phys, int size, u32 *dma_addr)
{
	struct video_buffer_export *exp;
	DEFINE_DMA_BUF_EXPORT_INFO(exp_info);
	unsigned long flags;
	int aligned_size;
	int ret;

	if (!video_buffer_dev || size <= 0)
		return -EINVAL;

	exp = kzalloc(sizeof(*exp), GFP_KERNEL);
	if (!exp)
		return -ENOMEM;

	aligned_size = PAGE_ALIGN(size);
	exp->phys = phys;
	exp->size = aligned_size;
	if (pfn_valid(PHYS_PFN(phys))) {
		unsigned int i;
		unsigned int nr_pages = aligned_size >> PAGE_SHIFT;
		struct page *pg = phys_to_page(phys);

		for (i = 0; i < nr_pages; i++, pg++) {
			void *kaddr = kmap_local_page(pg);
			memset(kaddr, 0, PAGE_SIZE);
			kunmap_local(kaddr);
		}
	}
	ret = sg_alloc_table(&exp->backing, 1, GFP_KERNEL);
	if (ret) {
		kfree(exp);
		return ret;
	}
	sg_set_page(exp->backing.sgl, phys_to_page(phys), aligned_size,
		    offset_in_page(phys));
	sg_dma_address(exp->backing.sgl) = phys;
	sg_dma_len(exp->backing.sgl) = aligned_size;

	exp_info.exp_name = DECD_NAME;
	exp_info.owner = THIS_MODULE;
	exp_info.ops = &dec_video_buffer_dma_buf_ops;
	exp_info.size = aligned_size;
	exp_info.flags = O_RDWR;
	exp_info.priv = &exp->backing;
	exp->dbuf = dma_buf_export(&exp_info);
	if (IS_ERR(exp->dbuf)) {
		ret = PTR_ERR(exp->dbuf);
		sg_free_table(&exp->backing);
		kfree(exp);
		return ret;
	}
	exp->attach = dma_buf_attach(exp->dbuf, video_buffer_dev);
	if (IS_ERR(exp->attach)) {
		ret = PTR_ERR(exp->attach);
		dma_buf_put(exp->dbuf);
		sg_free_table(&exp->backing);
		kfree(exp);
		return ret;
	}
	exp->sgt = dma_buf_map_attachment(exp->attach, DMA_BIDIRECTIONAL);
	if (IS_ERR(exp->sgt)) {
		ret = PTR_ERR(exp->sgt);
		dma_buf_detach(exp->dbuf, exp->attach);
		dma_buf_put(exp->dbuf);
		sg_free_table(&exp->backing);
		kfree(exp);
		return ret;
	}
	exp->dma_addr = sg_dma_address(exp->sgt->sgl);
	video_buffer_last_size = aligned_size;
	video_buffer_last_phys = phys;
	video_buffer_last_dma = exp->dma_addr;
	if (dma_addr)
		*dma_addr = exp->dma_addr;
	spin_lock_irqsave(&video_buffer_export_lock, flags);
	list_add_tail(&exp->node, &video_buffer_export_list);
	spin_unlock_irqrestore(&video_buffer_export_lock, flags);
	return 0;
}

int video_buffer_unmap(u32 dma_addr)
{
	struct video_buffer_export *exp, *tmp;
	unsigned long flags;

	spin_lock_irqsave(&video_buffer_export_lock, flags);
	list_for_each_entry_safe(exp, tmp, &video_buffer_export_list, node) {
		if (exp->dma_addr == dma_addr) {
			list_del(&exp->node);
			spin_unlock_irqrestore(&video_buffer_export_lock, flags);
			dma_buf_unmap_attachment(exp->attach, exp->sgt, DMA_BIDIRECTIONAL);
			dma_buf_detach(exp->dbuf, exp->attach);
			dma_buf_put(exp->dbuf);
			sg_free_table(&exp->backing);
			kfree(exp);
			if (video_buffer_last_dma == dma_addr)
				video_buffer_last_dma = 0;
			return 0;
		}
	}
	spin_unlock_irqrestore(&video_buffer_export_lock, flags);
	return -ENOENT;
}

u32 video_info_buffer_init(struct dec_frame_submit_desc *desc)
{
	return lower_32_bits(desc->y_phys) + 4096;
}

static void clean_video_info_free_list(void)
{
	struct dec_video_info_page *page;

	list_for_each_entry(page, &dec_video_info_free_list, node)
		memset(page->vaddr, 0, PAGE_SIZE);
}

int video_info_memory_block_init(struct device *dev)
{
	struct reserved_mem *rmem;
	struct device_node *np;
	struct page **pages;
	unsigned int i;
	unsigned int nr_pages;
	void *vbase;
	struct dec_video_info_page *page_desc;

	np = of_parse_phandle(dev->of_node, "memory-region", 0);
	if (!np)
		return -ENODEV;
	rmem = of_reserved_mem_lookup(np);
	of_node_put(np);
	if (!rmem)
		return -ENODEV;

	nr_pages = DIV_ROUND_UP(rmem->size, PAGE_SIZE);
	pages = vmalloc(array_size(nr_pages, sizeof(*pages)));
	if (!pages)
		return -ENOMEM;
	for (i = 0; i < nr_pages; i++)
		pages[i] = phys_to_page(rmem->base + i * PAGE_SIZE);
	vbase = vmap(pages, nr_pages, VM_MAP, pgprot_kernel);
	vfree(pages);
	if (!vbase)
		return -ENOMEM;

	INIT_LIST_HEAD(&dec_video_info_free_list);
	INIT_LIST_HEAD(&dec_video_info_used_list);
	for (i = 0; i < nr_pages; i++) {
		page_desc = kzalloc(sizeof(*page_desc), GFP_KERNEL);
		if (!page_desc)
			return -ENOMEM;
		page_desc->vaddr = vbase + i * PAGE_SIZE;
		page_desc->paddr = rmem->base + i * PAGE_SIZE;
		page_desc->index = i;
		list_add_tail(&page_desc->node, &dec_video_info_free_list);
	}
	clean_video_info_free_list();
	video_info_block_start = vbase;
	return 0;
}

void video_info_memory_block_exit(void)
{
	struct dec_video_info_page *page, *tmp;

	list_for_each_entry_safe(page, tmp, &dec_video_info_free_list, node) {
		list_del(&page->node);
		kfree(page);
	}
	list_for_each_entry_safe(page, tmp, &dec_video_info_used_list, node) {
		list_del(&page->node);
		kfree(page);
	}
	if (video_info_block_start)
		vunmap(video_info_block_start);
	video_info_block_start = NULL;
	INIT_LIST_HEAD(&dec_video_info_free_list);
	INIT_LIST_HEAD(&dec_video_info_used_list);
}

static struct dec_video_info_page *alloc_video_info_page(void)
{
	struct dec_video_info_page *page = NULL;
	unsigned long flags;

	spin_lock_irqsave(&dec_video_info_lock, flags);
	if (!list_empty(&dec_video_info_free_list)) {
		page = list_first_entry(&dec_video_info_free_list,
				      struct dec_video_info_page, node);
		list_del_init(&page->node);
		list_add_tail(&page->node, &dec_video_info_used_list);
	}
	spin_unlock_irqrestore(&dec_video_info_lock, flags);
	return page;
}

static void free_video_info_page(struct dec_video_info_page *page)
{
	unsigned long flags;

	if (!page)
		return;

	spin_lock_irqsave(&dec_video_info_lock, flags);
	list_del_init(&page->node);
	list_add_tail(&page->node, &dec_video_info_free_list);
	spin_unlock_irqrestore(&dec_video_info_lock, flags);
}

u32 video_info_buffer_init_dmabuf(struct dec_frame_item *item)
{
	struct dec_video_info_page *page;
	struct iosys_map map;
	int ret;

	if (!item || !item->info_map || !item->info_map->dbuf)
		return 0;

	ret = dma_buf_begin_cpu_access(item->info_map->dbuf, DMA_FROM_DEVICE);
	if (ret)
		return 0;
	ret = dma_buf_vmap(item->info_map->dbuf, &map);
	if (ret) {
		dma_buf_end_cpu_access(item->info_map->dbuf, DMA_FROM_DEVICE);
		return 0;
	}
	page = alloc_video_info_page();
	if (!page) {
		dma_buf_vunmap(item->info_map->dbuf, &map);
		dma_buf_end_cpu_access(item->info_map->dbuf, DMA_FROM_DEVICE);
		return 0;
	}
	item->video_info_page = page;
	page->parent = item;
	memcpy(page->vaddr, map.vaddr + 4096, 0x104);
	((u32 *)page->vaddr)[25] = page->paddr + 144;
	((u32 *)page->vaddr)[26] = page->paddr + 172;
	/* IDA: magic validation 0x61766b40 = "@kva" */
	if (((u32 *)page->vaddr)[0] != 0x61766b40)
		pr_warn("video_info magic mismatch: 0x%x\n",
			((u32 *)page->vaddr)[0]);
	dma_buf_vunmap(item->info_map->dbuf, &map);
	dma_buf_end_cpu_access(item->info_map->dbuf, DMA_FROM_DEVICE);
	return page->paddr;
}

void video_info_buffer_deinit(struct dec_frame_item *item)
{
	if (item && item->video_info_page)
		free_video_info_page(item->video_info_page);
}

static struct dec_video_frame *dec_create_video_frame(u32 seqnum)
{
	struct dec_video_frame *vf;

	vf = kzalloc(sizeof(*vf), GFP_KERNEL);
	if (!vf)
		return NULL;

	refcount_set(&vf->refcount, 1);
	vf->seqnum = seqnum;
	INIT_LIST_HEAD(&vf->node);
	return vf;
}

struct dec_dma_map *dec_dma_map(int fd, struct device *dev)
{
	struct dec_dma_map *map;

	if (fd < 0 || !dev)
		return NULL;

	map = kzalloc(sizeof(*map), GFP_KERNEL);
	if (!map)
		return NULL;

	map->dev = dev;
	map->dbuf = dma_buf_get(fd);
	if (IS_ERR(map->dbuf))
		goto err_free;
	map->attach = dma_buf_attach(map->dbuf, dev);
	if (IS_ERR(map->attach))
		goto err_put;
	map->sgt = dma_buf_map_attachment(map->attach, DMA_BIDIRECTIONAL);
	if (IS_ERR(map->sgt))
		goto err_detach;
	map->dma_addr = sg_dma_address(map->sgt->sgl);
	return map;

err_detach:
	dma_buf_detach(map->dbuf, map->attach);
err_put:
	dma_buf_put(map->dbuf);
err_free:
	kfree(map);
	return NULL;
}

void dec_dma_unmap(struct dec_dma_map *map)
{
	if (!map)
		return;

	dma_buf_unmap_attachment(map->attach, map->sgt, DMA_BIDIRECTIONAL);
	dma_buf_detach(map->dbuf, map->attach);
	dma_buf_put(map->dbuf);
	kfree(map);
}

size_t dec_dma_buf_size(struct dec_dma_map *map)
{
	struct scatterlist *sg;
	unsigned int i;
	size_t len = 0;

	if (!map || !map->sgt)
		return 0;

	for_each_sg(map->sgt->sgl, sg, map->sgt->nents, i)
		len += sg->length;

	return len;
}

/*
 * fmt_attr_tbl — IDA global at 0x81a0
 * 8 entries × 10 dwords each. Entry[0]=format_id, Entry[1]=bpp_class.
 * If entry[1]==8 → multiplier=1, else multiplier=2.
 * Stride = width * multiplier, aligned to desc->align.
 * C-addr = Y-DMA-addr + height * stride.
 */
static const u32 fmt_attr_tbl[8][10] = {
	{  6,  8, 1, 1, 1, 1, 0, 1, 3, 1 },
	{  4,  8, 1, 1, 1, 1, 0, 1, 1, 1 },
	{  2,  8, 2, 2, 1, 1, 1, 0, 2, 1 },
	{  0,  8, 2, 2, 2, 2, 1, 0, 3, 2 },
	{  5, 10, 1, 1, 1, 1, 0, 0, 6, 1 },
	{  3, 10, 2, 2, 1, 1, 1, 0, 4, 1 },
	{  1, 10, 2, 2, 2, 2, 0, 0, 3, 1 },
	{ 20, 10, 2, 2, 2, 2, 0, 0, 3, 1 },
};

/*
 * frame_item_create — IDA 0x202c
 *
 * Two paths: linear (desc->linear != 0) and DMA-buf.
 *
 * DMA-buf path:
 *   1. validate format (search fmt_attr_tbl)
 *   2. alloc 88-byte item, refcount=1
 *   3. map image dma-buf from desc->image_fd
 *   4. map info dma-buf from desc->info_fd
 *   5. video_info_buffer_init_dmabuf(item)
 *   6. compute Y/C addresses from format table:
 *      - multiplier = (entry[1]==8) ? 1 : 2
 *      - stride = width * multiplier, aligned to desc->align
 *      - C_addr = Y_dma + height * stride
 *   7. handle split-field mode
 *   8. alloc fence
 *   9. trace dma-buf map
 *
 * Linear path:
 *   - no dma-buf, Y/C from desc->y_phys/c_phys
 *   - video_info_buffer_init(desc)
 */
struct dec_frame_item *frame_item_create(struct dec_device *dec,
					 struct dec_frame_submit_desc *desc)
{
	struct dec_frame_item *item;
	u32 y_dma, c_offset;
	u32 stride, multiplier;
	int i;

	/* IDA: linear path check at byte offset 104 */
	if (desc->linear) {
		item = kzalloc(sizeof(*item), GFP_KERNEL);
		if (!item)
			return NULL;
		refcount_set(&item->refcount, 1);
		item->video_info_addr = video_info_buffer_init(desc);
		item->y_addr = desc->y_phys;
		item->c_addr = desc->c_phys;
		goto setup_fields;
	}

	/* IDA: format validation — search table, reject if format > 0x14 */
	if (desc->format > 0x14)
		return NULL;

	item = kzalloc(sizeof(*item), GFP_KERNEL);
	if (!item) {
		dev_err(dec->dev, "Kmalloc frame_item fail!\n");
		return NULL;
	}
	refcount_set(&item->refcount, 1);

	item->image_map = dec_dma_map(desc->image_fd, dec->dev);
	if (!item->image_map) {
		dev_err(dec->dev, "image dma map fail!\n");
		goto err_free;
	}
	item->info_map = dec_dma_map(desc->info_fd, dec->dev);
	if (!item->info_map) {
		dev_err(dec->dev, "image dma map fail!\n");
		goto err_unmap_image;
	}
	item->video_info_addr = video_info_buffer_init_dmabuf(item);

	/* IDA: format table lookup for Y/C address computation */
	y_dma = item->image_map->dma_addr;
	c_offset = 0;

	if (!desc->linear) {
		for (i = 0; i < 8; i++) {
			if (fmt_attr_tbl[i][0] == desc->format)
				break;
		}
		if (i < 8) {
			multiplier = (fmt_attr_tbl[i][1] == 8) ? 1 : 2;
			stride = desc->width * multiplier;
			if (desc->align)
				stride = ALIGN(stride, desc->align);
			c_offset = desc->height * stride;
		}
	}

	item->y_addr = y_dma;
	item->y_aux = 0;
	item->c_addr = y_dma + c_offset;
	item->c_aux = 0;
	item->format_shadow = 0;

setup_fields:
	/* IDA: split-field handling at desc byte 96 */
	if (desc->split_fields) {
		u64 field_offset = item->y_addr;
		u64 field_c_offset = item->c_addr;

		item->alt_y_valid = true;
		item->alt_c_valid = true;
		item->y_addr_alt = field_offset;
		item->c_addr_alt = field_c_offset;

		/* IDA: if desc->field_sel1 == 0 → swap primary/alt */
		if (!desc->field_sel1) {
			item->alt_c_valid = false;
			item->y_addr = item->y_addr_alt;
			item->y_addr_alt = field_offset;
			item->c_addr = item->c_addr_alt;
			item->c_addr_alt = field_c_offset;
		}
	} else {
		item->y_addr_alt = item->y_addr;
		item->c_addr_alt = item->c_addr;
	}

	/* IDA: alloc fence if fence_ctx exists */
	if (dec->fence_ctx)
		item->fence = dec_fence_alloc(dec->fence_ctx);

	/* IDA: trace dma buf map with (image_map, dma_addr, size, video_info) */
	if (item->image_map)
		dec_debug_trace_dma_buf_map(item);

	return item;

err_unmap_image:
	dec_dma_unmap(item->image_map);
err_free:
	kfree(item);
	return NULL;
}

/*
 * frame_item_release — IDA 0x23c4
 *
 * IDA shows on refcount→0:
 *   1. dec_fence_signal(item+52)
 *   2. dec_fence_free(item+52)
 *   3. item+52 = 0
 *   4. dec_debug_trace_dma_buf_unmap(item->image_map, item->image_map->dma_addr)
 *   5. dec_dma_unmap(item->image_map)
 *   6. dec_dma_unmap(item->info_map)
 *   7. video_info_buffer_deinit(item)
 *   8. kfree(item)
 */
void frame_item_release(void *payload)
{
	struct dec_frame_item *item = payload;

	if (!item)
		return;
	if (!refcount_dec_and_test(&item->refcount))
		return;

	if (item->fence) {
		dec_fence_signal(item->fence);
		/* IDA: dec_fence_free then clear pointer */
		kfree(item->fence);
		item->fence = NULL;
	}
	/* IDA: trace unmap with (image_map, image_map->dma_addr) */
	if (item->image_map)
		dec_debug_trace_dma_buf_unmap(item);
	dec_dma_unmap(item->image_map);
	dec_dma_unmap(item->info_map);
	video_info_buffer_deinit(item);
	kfree(item);
}

static void video_frame_put(struct dec_video_frame *vf)
{
	if (!vf)
		return;

	if (!refcount_dec_and_test(&vf->refcount))
		return;

	if (vf->release)
		vf->release(vf->payload);
	kfree(vf);
}

static void dec_frame_defer_release(struct dec_frame_queue *q,
				    struct dec_video_frame *vf)
{
	if (q->last_released)
		kfifo_in(&q->release_fifo, &q->last_released, 1);
	q->last_released = vf;
}

static int dec_frame_queue_enqueue(struct dec_frame_queue *q,
				   struct dec_video_frame *vf)
{
	if (!q || !vf)
		return -EINVAL;
	if (q->dirty)
		return 1;

	dec_frame_defer_release(q, q->slots[3]);
	q->slots[0] = vf;
	q->slots[1] = vf;
	q->slots[2] = vf;
	q->slots[3] = vf;
	refcount_inc(&vf->refcount);
	q->soft_repeat_count = 0;
	q->dirty = 1;
	return 0;
}

static struct dec_video_frame *dec_frame_pop(struct dec_frame_manager *fmgr)
{
	struct dec_video_frame *vf = NULL;
	unsigned long flags;

	spin_lock_irqsave(&fmgr->ready_lock, flags);
	if (fmgr->type == 1 && fmgr->interlace_pair[1]) {
		vf = fmgr->interlace_pair[(fmgr->queue->soft_repeat_count & 1)];
		refcount_inc(&vf->refcount);
		fmgr->queue->soft_repeat_count++;
	} else if (!list_empty(&fmgr->ready_list)) {
		vf = list_first_entry(&fmgr->ready_list, struct dec_video_frame, node);
		list_del_init(&vf->node);
		fmgr->ready_count--;
	}
	spin_unlock_irqrestore(&fmgr->ready_lock, flags);
	return vf;
}

/*
 * dec_frame_release_process — IDA 0x51ac
 *
 * IDA shows explicit spin_lock/unlock around each kfifo_out.
 * While fifo has >1 entries: lock, pop, unlock, put.
 * Then: if !dirty, lock, pop, unlock → last_frame.
 */
static void dec_frame_release_process(struct work_struct *work)
{
	struct dec_frame_queue *q = container_of(work, struct dec_frame_queue,
					      release_work);
	struct dec_video_frame *vf = NULL;
	unsigned long flags;
	int got;

	while (kfifo_len(&q->release_fifo) > 1) {
		spin_lock_irqsave(&q->lock, flags);
		got = kfifo_out(&q->release_fifo, &vf, 1);
		spin_unlock_irqrestore(&q->lock, flags);
		if (got == 1 && vf) {
			video_frame_put(vf);
			vf = NULL;
		}
	}

	if (!q->dirty) {
		spin_lock_irqsave(&q->lock, flags);
		got = kfifo_out(&q->release_fifo, &vf, 1);
		spin_unlock_irqrestore(&q->lock, flags);
		if (got == 1)
			last_frame = vf;
	}
}

/*
 * dec_frame_recycle — IDA 0x5668
 *
 * IDA signature: dec_frame_recycle(int fmgr_recycle_base, int queue, int unused)
 *   - drains kfifo at fmgr_recycle_base+56
 *   - for each item: lock queue, kfifo_in queue+4, unlock queue
 *   - then queue_work_on(4, system_wq, queue+24)
 *
 * In our port: fmgr has recycle_fifo, q has lock + release_fifo + release_work.
 * The function IS called under queue lock from dec_vsync_process, BUT IDA shows
 * it takes its OWN lock (raw_spin_lock_irqsave(a2)). This means the caller
 * does NOT hold the queue lock when calling recycle — or it's a different lock.
 * Looking at dec_vsync_process more carefully, recycle is called AFTER
 * spin_unlock_irqrestore, so the queue lock is NOT held. The recycle function
 * locks the queue itself.
 */
static void dec_frame_recycle(struct dec_frame_manager *fmgr,
			      struct dec_frame_queue *q)
{
	struct dec_video_frame *vf = NULL;
	unsigned long flags;

	while (kfifo_out(&fmgr->recycle_fifo, &vf, 1) == 1) {
		if (vf) {
			spin_lock_irqsave(&q->lock, flags);
			kfifo_in(&q->release_fifo, &vf, 1);
			spin_unlock_irqrestore(&q->lock, flags);
			vf = NULL;
		}
	}
	queue_work_on(4, system_wq, &q->release_work);
}

static int dec_frame_queue_hardware_repeat_ctrl(struct dec_frame_queue *q,
					int enable)
{
	int prev = q->hw_repeat;

	if (prev == enable)
		return 0;
	if (enable)
		prev = 0;
	q->hw_repeat = enable;
	if (enable)
		q->hw_repeat_prev = prev;
	q->hw_repeat_req = enable;
	return 1;
}

static int dec_frame_queue_repeat(struct dec_frame_queue *q)
{
	if (q->interlace) {
		q->soft_repeat_count++;
		if (q->toggle) {
			q->toggle = 1;
			if (dec_frame_queue_hardware_repeat_ctrl(q, 1))
				q->dirty = 1;
		} else {
			dec_frame_defer_release(q, q->slots[3]);
			if (q->slots[0])
				refcount_inc(&q->slots[0]->refcount);
			q->toggle = 1;
			q->dirty = 1;
			q->slots[3] = q->slots[2];
			q->slots[2] = q->slots[1];
			q->field_pattern = (2 * q->field_pattern) | 1;
			q->slots[0] = q->interlace_hold;
		}
	} else {
		dec_frame_defer_release(q, q->slots[3]);
		q->slots[3] = q->slots[2];
		q->slots[2] = q->slots[1];
		if (q->slots[0])
			refcount_inc(&q->slots[0]->refcount);
		q->dirty = 1;
		q->soft_repeat_count++;
	}
	return 0;
}

static int dec_is_interlace_frame(void *payload)
{
	struct dec_frame_item *item = payload;

	return item && item->alt_y_valid;
}

static int dec_frame_queue_make_interlace_pause_sequence(struct dec_frame_queue *q)
{
	dec_frame_defer_release(q, q->slots[2]);
	if (q->slots[1])
		refcount_inc(&q->slots[1]->refcount);
	q->slots[2] = q->slots[1];
	q->field_pattern = 11;
	return 0;
}

int dec_frame_manager_set_stream_type(struct dec_frame_manager *fmgr, int type)
{
	unsigned long flags;

	spin_lock_irqsave(&fmgr->ready_lock, flags);
	fmgr->type = type;
	spin_unlock_irqrestore(&fmgr->ready_lock, flags);
	return 0;
}

static int dec_frame_queue_resume(struct dec_frame_manager *fmgr)
{
	struct dec_frame_queue *q = fmgr->queue;
	struct dec_video_frame *vf;
	unsigned long flags;

	if (fmgr->state) {
		if (fmgr->state == 2)
			fmgr->state = 1;
		return 0;
	}

	spin_lock_irqsave(&q->lock, flags);
	if (!q->dirty) {
		if (last_frame) {
			video_frame_put(last_frame);
			last_frame = NULL;
		}
		vf = dec_frame_pop(fmgr);
		if (vf) {
			q->slots[0] = vf;
			q->slots[1] = vf;
			q->slots[2] = vf;
			q->slots[3] = vf;
			refcount_inc(&vf->refcount);
			if (dec_is_interlace_frame(vf->payload)) {
				dec_frame_manager_set_stream_type(fmgr, 1);
				q->interlace_hold = vf;
				q->interlace = 1;
				q->toggle = 0;
				q->field_pattern = 0;
			} else {
				if (fmgr->force_interlace) {
					dec_frame_manager_set_stream_type(fmgr, 1);
					q->interlace = 0;
					q->toggle = 0;
					q->field_pattern = 0;
				} else {
					/* IDA: memset(v4+2, 0, 0x14) = clear 5 dwords:
					 * interlace, toggle, field_pattern,
					 * repeat_current, repeat_budget */
					q->interlace = 0;
					q->toggle = 0;
					q->field_pattern = 0;
					q->repeat_current = 0;
					q->repeat_budget = 0;
					dec_frame_manager_set_stream_type(fmgr, 0);
				}
				video_frame_put(vf);
			}
			/* IDA: v4[11]=1 = armed flag on interlace_hold slot */
			q->interlace_hold = (void *)1;
			q->dirty = 1;
			q->soft_repeat_count = 0;
			q->repeat_budget = 1;
			fmgr->state = 1;
		}
	}
	spin_unlock_irqrestore(&q->lock, flags);
	return 0;
}

/*
 * dec_frame_manager_free — IDA 0x52b8
 *
 * IDA: lock → detach ready_list into local → save+clear interlace_pair →
 * clear type/request/ready_count → unlock →
 * iterate LOCAL detached list → video_frame_put each →
 * video_frame_put(saved pair[0]) → video_frame_put(saved pair[1])
 */
static void dec_frame_manager_free(struct dec_frame_manager *fmgr)
{
	struct dec_video_frame *vf, *tmp;
	struct dec_video_frame *pair0, *pair1;
	unsigned long flags;
	LIST_HEAD(detached);

	spin_lock_irqsave(&fmgr->ready_lock, flags);
	list_splice_init(&fmgr->ready_list, &detached);
	fmgr->ready_count = 0;
	pair0 = fmgr->interlace_pair[0];
	pair1 = fmgr->interlace_pair[1];
	fmgr->interlace_pair[0] = NULL;
	fmgr->interlace_pair[1] = NULL;
	fmgr->type = 0;
	fmgr->request = 0;
	fmgr->ready_count = 0;
	spin_unlock_irqrestore(&fmgr->ready_lock, flags);

	list_for_each_entry_safe(vf, tmp, &detached, node) {
		list_del_init(&vf->node);
		video_frame_put(vf);
	}
	video_frame_put(pair0);
	video_frame_put(pair1);
	fmgr->state = 0;
}

static void dec_frame_queue_sync(struct dec_frame_queue *q, bool blank_all)
{
	int i;
	bool alt_field;
	void *payload;
	void *payload_slot;

	q->dirty = 0;
	for (i = 0; i < 4; i++) {
		alt_field = !!((q->field_pattern >> i) & 1);
		if (q->slots[i]) {
			payload = q->slots[i]->payload;
			payload_slot = payload;
			if (q->sync_cb)
				q->sync_cb(q->dec, payload_slot, false, i, alt_field);
		} else if (!blank_all) {
			payload_slot = NULL;
			if (q->sync_cb)
				q->sync_cb(q->dec, payload_slot, true, i, alt_field);
		}
	}

	if (q->repeat_pending) {
		q->repeat_pending = 0;
		dec_reg_int_to_display_atomic(q->dec->regs);
	}
}

static void dec_vsync_process(struct dec_frame_manager *fmgr)
{
	struct dec_frame_queue *q = fmgr->queue;
	unsigned long flags;
	int state;

	spin_lock_irqsave(&q->lock, flags);
	state = fmgr->state;
	if (q->dirty) {
		dec_frame_queue_sync(q, state != 1);
		dec_frame_recycle(fmgr, q);
	} else if (q->hw_repeat_req) {
		if (q->slots[0]) {
			if (q->repeat_ctrl_cb)
				q->repeat_ctrl_cb(q->dec->regs, q->repeat_mode);
			dec_sync_interlace_cfg_to_hardware(q->dec->regs, q->slots[0]);
		}
	}
	spin_unlock_irqrestore(&q->lock, flags);

	if ((state & ~2) != 0) {
		if (!test_and_set_bit(0, &fmgr->refresh_scheduled))
			tasklet_schedule(&fmgr->refresh_tasklet);
	} else if (!state && waitqueue_active(&fmgr->waitq)) {
		wake_up(&fmgr->waitq);
	}
	fmgr->irq_count++;
}

static void dec_frame_queue_refresh(unsigned long data)
{
	struct dec_frame_manager *fmgr = (void *)data;
	struct dec_frame_queue *q = fmgr->queue;
	struct dec_video_frame *vf;
	unsigned long flags;

	clear_bit(0, &fmgr->refresh_scheduled);
	spin_lock_irqsave(&q->lock, flags);
	if (fmgr->state == 1) {
		if (!q->dirty) {
			if (q->interlace) {
				if (!q->toggle) {
					q->toggle = 1;
					if (q->hw_repeat_req) {
						q->repeat_pending = 1;
						q->repeat_mode = 1;
						if (!list_empty(&fmgr->ready_list)) {
							q->hw_repeat_req = 0;
							q->hw_repeat = 0;
							q->hw_repeat_prev = 1;
							q->repeat_current = 1;
						}
					}
				} else {
					q->toggle = 0;
					if (list_empty(&fmgr->ready_list) && q->repeat_budget <= 4) {
						q->repeat_budget++;
						q->repeat_current = 0;
						q->interlace_bottom = NULL;
						q->field_pattern <<= 1;
						dec_frame_queue_enqueue(q, q->interlace_hold);
						dec_debug_trace_frame(lower_32_bits(((struct dec_frame_item *)q->interlace_hold->payload)->y_addr), 0);
					} else if (q->hw_repeat_req) {
						q->repeat_current++;
						if (dec_frame_queue_hardware_repeat_ctrl(q, 1)) {
							if (q->repeat_ctrl_cb)
								q->repeat_ctrl_cb(q->dec->regs, 1);
							fmgr->state = 0;
						}
						q->repeat_mode = 0;
					} else if (!list_empty(&fmgr->ready_list)) {
						vf = dec_frame_pop(fmgr);
						q->repeat_mode = 0;
						q->repeat_current = 0;
						q->field_pattern <<= 1;
						dec_frame_defer_release(q, q->interlace_hold);
						q->interlace_hold = vf;
						q->repeat_budget++;
						fmgr->force_interlace = 0;
					}
				}
			} else if (!fmgr->force_interlace) {
				vf = dec_frame_pop(fmgr);
				if (vf) {
					if (dec_frame_queue_enqueue(q, vf)) {
						/* IDA 0x579c: enqueue failed (dirty),
						 * re-insert into ready_list if not interlace,
						 * else drop */
						unsigned long rflags;
						spin_lock_irqsave(&fmgr->ready_lock, rflags);
						if (fmgr->type == 1) {
							video_frame_put(vf);
						} else {
							list_add(&vf->node, &fmgr->ready_list);
							fmgr->ready_count++;
						}
						spin_unlock_irqrestore(&fmgr->ready_lock, rflags);
					} else {
						/* enqueue OK → drop caller ref */
						video_frame_put(vf);
					}
					fmgr->force_interlace = 0;
				} else {
					dec_frame_queue_repeat(q);
					fmgr->force_interlace = 1;
				}
			} else if (fmgr->interlace_pair[0] && fmgr->interlace_pair[1]) {
				q->toggle ^= 1;
				q->field_pattern <<= 1;
				if (q->toggle)
					dec_frame_queue_enqueue(q, fmgr->interlace_pair[1]);
				else
					dec_frame_queue_enqueue(q, fmgr->interlace_pair[0]);
			}
		}
	} else if (fmgr->state == 3) {
		if (!q->dirty) {
			if ((int)q->shutdown_counter < 0) {
				dec_frame_queue_repeat(q);
			} else if (q->interlace) {
				fmgr->state = 4;
				q->repeat_mode = 0;
				q->soft_repeat_count = 0;
				q->repeat_budget = 0;
				q->dirty = 1;
			} else {
				fmgr->state = 2;
			}
		}
	} else if (fmgr->state == 4) {
		if (!q->dirty) {
			if ((int)q->shutdown_counter < 0) {
				dec_frame_queue_repeat(q);
			} else {
			fmgr->state = 5;
			q->soft_repeat_count = 0;
			q->shutdown_hold = q->slots[0] ? q->slots[0] : q->slots[1];
			if (!q->shutdown_hold && q->slots[0]) {
				refcount_inc(&q->slots[0]->refcount);
				q->shutdown_hold = q->slots[0];
			}
			dec_frame_defer_release(q, q->slots[0]);
			q->slots[0] = NULL;
			q->slots[1] = NULL;
			q->slots[2] = NULL;
			q->slots[3] = NULL;
			q->toggle = 0;
			q->field_pattern = 0;
			q->repeat_current = 0;
			q->repeat_mode = 0;
			q->repeat_pending = 0;
			q->hw_repeat = 0;
			q->hw_repeat_prev = 0;
			q->hw_repeat_req = 0;
			q->dirty = 1;
			q->interlace_bottom = NULL;
			q->interlace_top = NULL;
			q->interlace_hold = NULL;
			q->soft_repeat_count = 0;
			q->repeat_budget = 0;
			}
		}
	} else if (fmgr->state == 5) {
		if (!q->dirty) {
			if ((int)q->shutdown_counter < 0) {
				dec_frame_queue_repeat(q);
			} else {
			dec_frame_defer_release(q, q->shutdown_hold);
			if (q->slots[0])
				dec_frame_defer_release(q, q->slots[0]);
			if (q->last_released)
				kfifo_in(&q->release_fifo, &q->last_released, 1);
			q->last_released = NULL;
			q->shutdown_hold = NULL;
			q->slots[0] = NULL;
			fmgr->state = 0;
			dec_frame_queue_hardware_repeat_ctrl(q, 0);
			dec_frame_recycle(fmgr, q);
			}
		}
	}
	spin_unlock_irqrestore(&q->lock, flags);
	if (!fmgr->state)
		wake_up(&fmgr->waitq);
}

struct dec_frame_manager *dec_frame_manager_init(void)
{
	struct dec_frame_manager *fmgr;
	struct dec_frame_queue *q;

	fmgr = kzalloc(sizeof(*fmgr), GFP_KERNEL);
	if (!fmgr)
		return NULL;

	q = kzalloc(sizeof(*q), GFP_KERNEL);
	if (!q) {
		kfree(fmgr);
		return NULL;
	}

	spin_lock_init(&fmgr->ready_lock);
	INIT_LIST_HEAD(&fmgr->ready_list);
	tasklet_init(&fmgr->refresh_tasklet, dec_frame_queue_refresh,
		     (unsigned long)fmgr);
	/* IDA 0x5f20: fmgr release_work = dec_frame_release_process at v0+148 */
	INIT_WORK(&fmgr->release_work, dec_frame_release_process);
	init_waitqueue_head(&fmgr->waitq);
	fmgr->queue = q;
	fmgr->self = fmgr;

	spin_lock_init(&q->lock);
	/* IDA: queue release_work is NOT explicitly initialized (kzalloc zeros it).
	 * The release work that calls dec_frame_release_process is on fmgr, not q.
	 * But dec_frame_release_process uses container_of(work, queue, release_work)
	 * so it MUST be on q. IDA shows queue_work_on(4, ..., a2+24) in recycle
	 * where a2 is the queue. So the queue's work IS used. We init both. */
	INIT_WORK(&q->release_work, dec_frame_release_process);
	/* IDA: v1[17] = 4 → queue->shutdown_counter = 4 */
	q->shutdown_counter = 4;
	if (kfifo_alloc(&q->release_fifo, 512 * sizeof(struct dec_video_frame *),
			GFP_KERNEL)) {
		kfree(q);
		kfree(fmgr);
		return NULL;
	}

	if (kfifo_alloc(&fmgr->recycle_fifo,
			512 * sizeof(struct dec_video_frame *), GFP_KERNEL)) {
		kfifo_free(&q->release_fifo);
		kfree(q);
		kfree(fmgr);
		return NULL;
	}

	return fmgr;
}

int dec_frame_manager_exit(struct dec_frame_manager *fmgr)
{
	if (!fmgr)
		return 0;

	tasklet_kill(&fmgr->refresh_tasklet);
	flush_work(&fmgr->release_work);
	kfifo_free(&fmgr->recycle_fifo);
	if (fmgr->queue) {
		kfifo_free(&fmgr->queue->release_fifo);
		kfree(fmgr->queue);
	}
	dec_frame_manager_free(fmgr);
	kfree(fmgr);
	return 0;
}

/*
 * dec_frame_manager_stop — IDA 0x6128
 *
 * IDA: if state in {1,2}: request=1, state=3.
 * Then if state!=0: wait_event_timeout(2500).
 * If timeout remaining > 0 (= didn't time out): free.
 */
int dec_frame_manager_stop(struct dec_frame_manager *fmgr)
{
	long remaining;

	if (!fmgr)
		return 0;

	if (fmgr->state == 1 || fmgr->state == 2) {
		fmgr->request = 1;
		fmgr->state = 3;
	}

	if (fmgr->state) {
		remaining = wait_event_timeout(fmgr->waitq,
					       fmgr->state == 0, 2500);
		if (remaining > 0)
			dec_frame_manager_free(fmgr);
	}

	return 0;
}

void dec_frame_manager_handle_vsync(struct dec_frame_manager *fmgr)
{
	if (fmgr)
		dec_vsync_process(fmgr);
}

int dec_frame_manager_enqueue_frame(struct dec_frame_manager *fmgr,
				    void *payload,
				    void (*release)(void *payload))
{
	struct dec_video_frame *vf;
	unsigned long flags;

	vf = dec_create_video_frame(fmgr->seqno++);
	if (!vf)
		return -ENOMEM;
	vf->payload = payload;
	vf->release = release;

	spin_lock_irqsave(&fmgr->ready_lock, flags);
	list_add_tail(&vf->node, &fmgr->ready_list);
	fmgr->ready_count++;
	spin_unlock_irqrestore(&fmgr->ready_lock, flags);

	/* IDA 0x63b8: dec_frame_queue_resume(a1) at end */
	dec_frame_queue_resume(fmgr);
	return 0;
}

int dec_frame_manager_enqueue_interlace_frame(struct dec_frame_manager *fmgr,
					      void *top,
					      void *bottom,
					      void (*release)(void *payload))
{
	struct dec_video_frame *top_vf;
	struct dec_video_frame *bot_vf;
	unsigned long flags;

	if (fmgr->type != 1)
		return -EINVAL;

	top_vf = dec_create_video_frame(fmgr->seqno++);
	bot_vf = dec_create_video_frame(fmgr->seqno++);
	if (!top_vf || !bot_vf) {
		video_frame_put(top_vf);
		video_frame_put(bot_vf);
		return -ENOMEM;
	}

	top_vf->payload = top;
	top_vf->release = release;
	bot_vf->payload = bottom;
	bot_vf->release = release;

	/*
	 * IDA 0x6474: lock ready_lock, set force_interlace=1, clear old pair
	 * via recycle_fifo (not video_frame_put!), then assign new pair,
	 * queue release work, unlock, and call dec_frame_queue_resume.
	 */
	spin_lock_irqsave(&fmgr->ready_lock, flags);
	fmgr->force_interlace = 1;
	/* IDA: old interlace pairs go into recycle fifo under lock */
	if (fmgr->interlace_pair[0]) {
		kfifo_in(&fmgr->recycle_fifo, &fmgr->interlace_pair[0], 1);
		fmgr->interlace_pair[0] = NULL;
	}
	if (fmgr->interlace_pair[1]) {
		kfifo_in(&fmgr->recycle_fifo, &fmgr->interlace_pair[1], 1);
		fmgr->interlace_pair[1] = NULL;
	}
	fmgr->interlace_pair[0] = top_vf;
	fmgr->interlace_pair[1] = bot_vf;
	spin_unlock_irqrestore(&fmgr->ready_lock, flags);

	queue_work_on(4, system_wq, &fmgr->queue->release_work);

	/* IDA 0x6474: dec_frame_queue_resume at end */
	dec_frame_queue_resume(fmgr);
	return 0;
}

int dec_frame_manager_register_sync_cb(struct dec_frame_manager *fmgr,
				       struct dec_device *dec,
				       void (*sync_cb)(struct dec_device *dec,
						       void *frame_payload,
						       bool blank,
						       int idx,
						       bool alt_field))
{
	unsigned long flags;

	spin_lock_irqsave(&fmgr->queue->lock, flags);
	fmgr->queue->dec = dec;
	fmgr->queue->sync_cb = sync_cb;
	spin_unlock_irqrestore(&fmgr->queue->lock, flags);
	return 0;
}

int dec_frame_manager_register_repeat_ctrl_pfn(struct dec_frame_manager *fmgr,
					       struct dec_reg_block *regs,
					       void (*repeat_ctrl_cb)(struct dec_reg_block *regs,
							       bool enable))
{
	unsigned long flags;

	spin_lock_irqsave(&fmgr->queue->lock, flags);
	fmgr->queue->repeat_ctrl_cb = repeat_ctrl_cb;
	spin_unlock_irqrestore(&fmgr->queue->lock, flags);
	return 0;
}

int dec_frame_manager_dump(struct dec_frame_manager *fmgr, char *buf)
{
	return sprintf(buf,
		       "video frame manager info:\n"
		       "           type: %u\n"
		       "  current state: %u\n"
		       "        request: %u\n"
		       "   frame seqnum: %u\n"
		       "       irqcount: %llu\n",
		       fmgr->type, fmgr->state, fmgr->request, fmgr->seqno,
		       fmgr->irq_count);
}
