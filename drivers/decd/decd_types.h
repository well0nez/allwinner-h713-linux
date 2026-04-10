// SPDX-License-Identifier: GPL-2.0
#pragma once

#include <linux/clk.h>
#include <linux/cdev.h>
#include <linux/device.h>
#include <linux/dma-buf.h>
#include <linux/dma-fence.h>
#include <linux/fs.h>
#include <linux/interrupt.h>
#include <linux/io.h>
#include <linux/kfifo.h>
#include <linux/list.h>
#include <linux/mutex.h>
#include <linux/platform_device.h>
#include <linux/poll.h>
#include <linux/reset.h>
#include <linux/spinlock.h>
#include <linux/types.h>
#include <linux/workqueue.h>

#define DECD_NAME "decd"
#define DECD_CLASS_NAME "decd"

#define DECD_DEFAULT_CLK_RATE 200000000U
#define DECD_VSYNC_RING_LEN 8

#define DECD_IOC_STOP_VIDEO_STREAM 0x40046408u
#define DECD_IOC_BYPASS_CONFIG     0x40046409u
#define DECD_IOC_PM_HINT           0x40046401u
#define DECD_IOC_FRAME_SUBMIT      0x40706400u
#define DECD_IOC_INTERLACE_SETUP   0x40706407u
#define DECD_IOC_GET_VSYNC_TS      0x8008640au
#define DECD_IOC_MAP_LINEAR_BUFFER 0xc010640bu

extern int sunxi_tvtop_client_register(struct device *dev);

struct dec_device;
struct dec_frame_manager;
struct dec_frame_item;

struct dec_linear_map_req {
	__u32 phys;
	__u32 size;
	__u32 dma_addr;
	__u32 reserved;
};

struct dec_frame_submit_desc {
	__u8 linear;
	__u8 reserved0[3];
	__s32 image_fd;
	__u32 format;
	__u32 reserved1[7];
	__u32 width;
	__u32 height;
	__u32 reserved2[4];
	__u32 align;
	__u32 reserved3[2];
	__s32 info_fd;
	__u32 reserved4[4];
	__u8 split_fields;
	__u8 invert_field;
	__u8 field_mode;
	__u8 field_repeat;
	__u32 field_sel0;
	__u32 field_sel1;
	__u64 y_phys;
	__u64 c_phys;
};

struct dec_interlace_setup_desc {
	struct dec_frame_submit_desc top;
	struct dec_frame_submit_desc bottom;
};

struct dec_ioctl_header {
	__u64 user_ptr;
	__u64 user_ptr2;
	__u32 arg0;
	__u32 reserved0;
	__u32 arg1;
	__u32 reserved1;
};

struct dec_reg_block {
	void __iomem *top;
	void __iomem *afbd;
	void __iomem *workaround;
	__u8 dirty;
};

struct dec_vsync_ring {
	spinlock_t lock;
	u64 ts[DECD_VSYNC_RING_LEN];
	u32 rd;
	u32 wr;
};

struct dec_fence_context {
	char name[32];
	u64 context;
	spinlock_t lock;
	u32 seqno;
};

struct dec_fence {
	struct dma_fence base;
	struct dec_fence_context *ctx;
	bool signaled;
};

struct dec_dma_map {
	struct dma_buf *dbuf;
	struct dma_buf_attachment *attach;
	struct sg_table *sgt;
	dma_addr_t dma_addr;
	struct device *dev;
};

struct dec_frame_item {
	struct dec_dma_map *image_map;
	struct dec_dma_map *info_map;
	u64 y_addr;
	u32 y_aux;
	u64 c_addr;
	u32 c_aux;
	u32 video_info_addr;
	u32 format_shadow;
	void *video_info_page;
	struct dec_fence *fence;
	bool alt_y_valid;
	bool alt_c_valid;
	u64 y_addr_alt;
	u64 c_addr_alt;
	refcount_t refcount;
};

struct dec_video_frame {
	refcount_t refcount;
	u32 seqnum;
	struct list_head node;
	void *payload;
	void (*release)(void *payload);
};

struct dec_frame_queue {
	spinlock_t lock;
	u32 dirty;
	u32 interlace;
	u32 toggle;
	u32 field_pattern;
	u32 repeat_current;
	u32 repeat_budget;
	struct dec_video_frame *slots[4];
	struct dec_video_frame *interlace_hold;
	struct dec_video_frame *interlace_top;
	struct dec_video_frame *interlace_bottom;
	DECLARE_KFIFO_PTR(release_fifo, struct dec_video_frame *);
	struct dec_device *dec;
	void (*sync_cb)(struct dec_device *dec, void *frame_payload,
			bool blank, int idx, bool alt_field);
	void (*repeat_ctrl_cb)(struct dec_reg_block *regs, bool enable);
	struct work_struct release_work;
	struct dec_video_frame *shutdown_hold;
	struct dec_video_frame *last_released;
	u32 repeat_mode;
	u32 repeat_pending;
	u32 hw_repeat;
	u32 hw_repeat_prev;
	u32 hw_repeat_req;
	u32 shutdown_counter;
	u32 soft_repeat_count;
};

struct dec_frame_manager {
	u32 seqno;
	u32 state;
	u32 request;
	u32 type;
	spinlock_t ready_lock;
	struct list_head ready_list;
	u32 ready_count;
	u32 force_interlace;
	struct dec_frame_queue *queue;
	u64 irq_count;
	struct tasklet_struct refresh_tasklet;
	unsigned long refresh_scheduled;
	DECLARE_KFIFO_PTR(recycle_fifo, struct dec_video_frame *);
	struct work_struct release_work;
	struct dec_frame_manager *self;
	wait_queue_head_t waitq;
	struct dec_video_frame *interlace_pair[2];
};

struct dec_debug_info {
	void __iomem *reg_base;
	u32 irq_count;
	u32 jiffies_hist[100];
	u32 jiffies_pos;
	struct work_struct work;
	u32 dbgdat[768];
	u32 frame_trace_pos;
	u32 exception_trace_pos;
};

struct dec_video_info_page {
	void *vaddr;
	phys_addr_t paddr;
	u32 index;
	void *parent;
	struct list_head node;
};

struct dec_device {
	struct device *dev;
	struct platform_device *pdev;
	struct cdev cdev;
	dev_t devt;
	struct class *class;
	struct device *chrdev;

	struct dec_reg_block *regs;
	int irq;
	u32 clk_rate;
	struct clk *clk_afbd;
	struct clk *clk_bus_disp;
	struct reset_control *rst_bus_disp;

	struct dec_debug_info *debug;
	struct attribute_group *attr_group;
	struct dec_fence_context *fence_ctx;
	struct dec_vsync_ring *vsync;
	struct dec_frame_manager *fmgr;
	wait_queue_head_t event_wait;
	struct mutex lock;
	bool enabled;
};

extern struct dec_device *g_dec;
extern struct dec_video_frame *last_frame;

int dec_frame_manager_enqueue_frame(struct dec_frame_manager *fmgr,
				    void *payload,
				    void (*release)(void *payload));
int dec_frame_manager_enqueue_interlace_frame(struct dec_frame_manager *fmgr,
					      void *top,
					      void *bottom,
					      void (*release)(void *payload));
struct dec_frame_manager *dec_frame_manager_init(void);
int dec_frame_manager_exit(struct dec_frame_manager *fmgr);
int dec_frame_manager_stop(struct dec_frame_manager *fmgr);
int dec_frame_manager_register_sync_cb(struct dec_frame_manager *fmgr,
				       struct dec_device *dec,
				       void (*sync_cb)(struct dec_device *dec,
						       void *frame_payload,
						       bool blank,
						       int idx,
						       bool alt_field));
int dec_frame_manager_register_repeat_ctrl_pfn(struct dec_frame_manager *fmgr,
					       struct dec_reg_block *regs,
					       void (*repeat_ctrl_cb)(struct dec_reg_block *regs,
							       bool enable));
int dec_frame_manager_dump(struct dec_frame_manager *fmgr, char *buf);
int dec_frame_manager_set_stream_type(struct dec_frame_manager *fmgr, int type);
void dec_frame_manager_handle_vsync(struct dec_frame_manager *fmgr);

struct dec_fence_context *dec_fence_context_alloc(const char *name);
struct dec_fence *dec_fence_alloc(struct dec_fence_context *ctx);
void dec_fence_signal(struct dec_fence *df);
int dec_fence_fd_create(struct dec_fence *df);

void dec_reg_top_enable(struct dec_reg_block *regs, bool on);
void dec_reg_enable(struct dec_reg_block *regs, bool on);
void dec_reg_mux_select(struct dec_reg_block *regs, u8 mux);
void dec_decoder_display_init(struct dec_reg_block *regs);
void dec_reg_int_to_display(struct dec_reg_block *regs);
void dec_reg_int_to_display_atomic(struct dec_reg_block *regs);
void dec_reg_blue_en(struct dec_reg_block *regs, bool on);
void dec_reg_set_filed_mode(struct dec_reg_block *regs, bool on);
void dec_reg_set_filed_repeat(struct dec_reg_block *regs, bool on);
void dec_reg_set_address(struct dec_reg_block *regs, u32 *planes, u32 aux,
			 char field, int idx);
int dec_reg_video_channel_attr_config(struct dec_reg_block *regs, u32 *cfg);
void dec_reg_set_dirty(struct dec_reg_block *regs, bool dirty);
bool dec_reg_is_dirty(struct dec_reg_block *regs);
u32 dec_reg_frame_cnt(struct dec_reg_block *regs);
u32 dec_reg_get_y_address(struct dec_reg_block *regs, int idx);
u32 dec_reg_get_c_address(struct dec_reg_block *regs, int idx);
void dec_reg_bypass_config(struct dec_reg_block *regs, u32 value);
int dec_irq_query(struct dec_reg_block *regs);
void dec_sync_interlace_cfg_to_hardware(struct dec_reg_block *regs,
					struct dec_video_frame *vf);

int dec_enable(struct dec_device *dec);
int dec_disable(struct dec_device *dec);
int dec_vsync_timestamp_get(struct dec_device *dec, u64 *ts);
__poll_t dec_event_poll(struct dec_device *dec, struct file *file,
			poll_table *wait);
irqreturn_t dec_vsync_handler(int irq, void *data);

int dec_stop_video_stream(struct dec_device *dec);
int dec_frame_submit(struct dec_device *dec,
		     struct dec_frame_submit_desc *desc,
		     int *release_fence_fd, int repeat);
int dec_interlace_setup(struct dec_device *dec,
			struct dec_interlace_setup_desc *desc);

struct dec_dma_map *dec_dma_map(int fd, struct device *dev);
void dec_dma_unmap(struct dec_dma_map *map);
size_t dec_dma_buf_size(struct dec_dma_map *map);
int video_buffer_map(u32 phys, int size, u32 *dma_addr);
int video_buffer_unmap(u32 dma_addr);
int video_buffer_dma_buf_attach(struct dma_buf *dmabuf,
				struct dma_buf_attachment *attach);
void video_buffer_dma_buf_detatch(struct dma_buf *dmabuf,
				 struct dma_buf_attachment *attach);
void video_buffer_dma_buf_release(struct dma_buf *dmabuf);
struct sg_table *video_buffer_map_dma_buf(struct dma_buf_attachment *attach,
					 enum dma_data_direction dir);
void video_buffer_unmap_dma_buf(struct dma_buf_attachment *attach,
				       struct sg_table *sgt,
				       enum dma_data_direction dir);
ssize_t dec_show_info(struct device *dev, struct device_attribute *attr,
		      char *buf);
ssize_t dec_show_frame_manager(struct device *dev,
			       struct device_attribute *attr, char *buf);
void dec_debug_trace_dma_buf_map(struct dec_frame_item *item);
void dec_debug_trace_dma_buf_unmap(struct dec_frame_item *item);
int dec_debug_trace_frame(int addr, int fmt);
int dec_debug_set_register_base(int base);
int dec_debug_record_exception(int a1, int a2);
int dec_debug_dump(int dst, int len, int a3, int a4);
int dec_debug_init(struct dec_device *dec);
int video_info_memory_block_init(struct device *dev);
void video_info_memory_block_exit(void);
u32 video_info_buffer_init(struct dec_frame_submit_desc *desc);
u32 video_info_buffer_init_dmabuf(struct dec_frame_item *item);
void video_info_buffer_deinit(struct dec_frame_item *item);
struct dec_frame_item *frame_item_create(struct dec_device *dec,
					 struct dec_frame_submit_desc *desc);
void frame_item_release(void *payload);

int dec_init(struct dec_device *dec);
void dec_exit(struct dec_device *dec);
